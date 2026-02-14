# Architecture & Design

A deep dive into the Agentic Payments Orchestrator — how it works, why it's built this way, and how every piece connects.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [High-Level Architecture](#high-level-architecture)
3. [Decision Flow](#decision-flow)
4. [Policy Engine](#policy-engine)
5. [Risk Scoring](#risk-scoring)
6. [LLM Agent Layer (Gemini)](#llm-agent-layer-gemini)
7. [Agent Orchestrator](#agent-orchestrator)
8. [Guardrails](#guardrails)
9. [Payment Execution Pipeline](#payment-execution-pipeline)
10. [Authentication & Authorization](#authentication--authorization)
11. [Data Model](#data-model)
12. [Tech Stack Rationale](#tech-stack-rationale)
13. [Security Considerations](#security-considerations)
14. [What This Is Not](#what-this-is-not)

---

## Problem Statement

Businesses process thousands of vendor payments daily. Manual review of every payment is slow; fully automated approval is risky. The goal is an **intelligent middle ground**:

- **Low-risk payments** (small amount, trusted vendor, normal pattern) are auto-approved and executed instantly.
- **Suspicious payments** (new vendor, unusual amount, velocity spike) are flagged for human review.
- **Policy violations** (over spending limits, blocked vendors) are blocked outright — no exceptions.

The system must be **auditable** (every decision traced), **safe** (AI can't bypass rules), and **fast** (sub-second decisions for normal payments).

---

## High-Level Architecture

```
                    ┌─────────────┐
                    │  Next.js    │
                    │  Dashboard  │
                    └──────┬──────┘
                           │ REST API
                    ┌──────▼──────┐
                    │   FastAPI   │
                    │   Backend   │
                    └──┬───┬───┬──┘
                       │   │   │
            ┌──────────┘   │   └──────────┐
            ▼              ▼              ▼
     ┌────────────┐ ┌───────────┐ ┌──────────────┐
     │  Policy    │ │   Risk    │ │   Gemini     │
     │  Engine    │ │  Scoring  │ │   LLM        │
     │ (rules)   │ │ (signals) │ │ (reasoning)  │
     └─────┬──────┘ └─────┬─────┘ └──────┬───────┘
           │               │              │
           └───────┬───────┘──────────────┘
                   ▼
          ┌────────────────┐
          │    Agent       │
          │  Orchestrator  │  ← Combines all three, applies decision rule
          └───────┬────────┘
                  │
        ┌─────────▼──────────┐
        │                    │
   BLOCK/REQUIRE       ALLOW_AUTOPAY
        │                    │
   Human Review         ┌────▼─────┐
   (Approval Queue)     │  Celery  │ ← Async task queue
        │               │  Worker  │
        │               └────┬─────┘
        │                    │
        │               ┌────▼─────┐
        └──► (on approve)│  Stripe  │ ← Payment execution
                        │  API     │
                        └────┬─────┘
                             │
                        ┌────▼─────┐
                        │  Audit   │ ← Immutable log
                        │  Trail   │
                        └──────────┘
```

---

## Decision Flow

Every payment request follows this exact sequence:

### Step 1: Validation
- Is the vendor valid and not blocked?
- Is the request body well-formed?
- Is the idempotency key unique?

### Step 2: Policy Engine (Deterministic)
All active policies are evaluated against the payment. Each returns one of:
- `ALLOW_AUTOPAY` — no issues
- `REQUIRE_APPROVAL` — needs human review
- `BLOCK` — hard rejection

The **most restrictive** verdict wins. If any rule says BLOCK, the overall verdict is BLOCK regardless of what other rules say.

### Step 3: Risk Scoring (Deterministic)
Eleven risk signals are computed from database queries, grouped into original and enhanced categories:
- **Original (5):** new vendor, first payment, unusual amount, typo-squatting, off-hours
- **Enhanced (6):** statistical outlier, velocity spike, round large amount, category mismatch, weekend large amount, rapid escalation
- Each has a severity weight; they're summed with **correlation-aware bonuses** into a composite score (0-100)
- A `VendorContext` is built: vendor age, total payments, average amount, dominant category, and recent payment history

### Step 4: LLM Analysis (Gemini)
If the policy verdict is NOT BLOCK, the full enriched context is sent to Gemini:
- Payment details + policy verdict + triggered rules + risk signals + composite score
- **Vendor Profile**: age, status, total payments, average amount, dominant category
- **Recent Payment History**: last 5 payments with amounts, categories, statuses, and recency
- Gemini evaluates across 4 dimensions (pattern fit, signal correlation, description plausibility, human review heuristic) and returns a structured JSON assessment with `should_escalate` flag

If the policy verdict IS BLOCK, Gemini is skipped entirely (no point consulting AI on something that's already blocked).

### Step 5: Decision Rule (Escalation Only)
This is the critical constraint:

| Policy Verdict | Agent Escalates? | Final Decision |
|---|---|---|
| BLOCK | *(not called)* | **BLOCK** |
| REQUIRE_APPROVAL | *(doesn't matter)* | **REQUIRE_APPROVAL** |
| ALLOW_AUTOPAY | Yes | **REQUIRE_APPROVAL** (escalated) |
| ALLOW_AUTOPAY | No | **APPROVED** (auto-pay) |

The agent can only move decisions **up** in severity. Never down.

### Step 6: Execution or Queue
- `APPROVED` → Celery task dispatched → Stripe payment created → status becomes `COMPLETED`
- `REQUIRE_APPROVAL` → Sits in approval queue → Human approves/rejects → If approved, goes to Celery/Stripe
- `BLOCKED` → Logged and done. No further action.

### Step 7: Audit
Every step is recorded: policy evaluation results, agent reasoning, risk signals, approval decisions, payment execution results.

---

## Policy Engine

Located in `backend/app/services/policy_engine.py`.

The policy engine is a pure function: given a payment and a database connection, it returns a verdict. No AI, no randomness, no external calls.

### Rule Types

| Rule Type | What It Checks | Verdict |
|---|---|---|
| `MAX_TXN` | Single payment amount > max | BLOCK |
| `DAILY_CAP` | Vendor's daily total would exceed cap | BLOCK |
| `MONTHLY_CAP` | Vendor's monthly total would exceed cap | BLOCK |
| `VELOCITY` | Too many payments to vendor in time window | REQUIRE_APPROVAL |
| `VENDOR_ALLOWLIST` | Vendor status is not ACTIVE | BLOCK |
| `CATEGORY_BUDGET` | Category monthly spend would exceed budget | BLOCK |
| `APPROVAL_THRESHOLD` | Amount exceeds threshold | REQUIRE_APPROVAL |

### Idempotency Check
Runs on every payment regardless of policies. If a payment with the same `idempotency_key` already exists, it's blocked at the database level (unique constraint) and returns a 409.

### How Rules Are Stored
Policies are database rows, not hard-coded. Each has:
- `name` — human-readable label
- `rule_type` — maps to a rule evaluator function
- `parameters` — JSON object (e.g., `{"max_amount": 50000}`)
- `priority` — evaluation order
- `is_active` — can be toggled without deleting

This means policies can be created, modified, and deactivated through the API without code changes.

### Evaluation Strategy
All active policies are fetched, sorted by priority, and evaluated sequentially. Every triggered rule is collected (not just the first one). The most restrictive verdict across all rules becomes the final policy verdict.

---

## Risk Scoring

Located in `backend/app/services/risk_scoring.py`.

Deterministic risk signals computed from database state. These don't make decisions — they provide context for the LLM. The module also builds a `VendorContext` that gives the LLM a structured profile of the vendor and their recent payment history.

### Original Signals (5)

| Signal | Severity | Logic |
|---|---|---|
| `new_vendor` | Medium (25) | Vendor created < 7 days ago |
| `first_payment` | Medium (25) | Zero prior payments to this vendor |
| `high_amount_vs_average` | High (40) | Amount > 2× vendor's historical average |
| `typo_squatting` | High (40) | Vendor name 75-99% similar to another vendor (SequenceMatcher) |
| `outside_business_hours` | Low (10) | Submitted on weekend or outside 9-17 UTC |

### Enhanced Signals (6)

| Signal | Severity | Logic |
|---|---|---|
| `amount_statistical_outlier` | High (35) | Amount > mean + 2σ of vendor's payment history (needs ≥3 payments) |
| `velocity_spike` | Medium (30) | Payments in last 24h ≥ 3× the 30-day daily average |
| `round_amount_large` | Low (15) | Amount ≥ $5,000 AND is a round number (divisible by 1000) |
| `category_mismatch` | Medium (30) | Payment category differs from vendor's dominant category (needs ≥5 payments, 70%+ dominance) |
| `weekend_large_amount` | Medium (20) | Weekend submission AND amount > $10,000 |
| `rapid_escalation` | High (35) | Last 3 payments show monotonically increasing amounts with final ≥ 2× first |

### Correlation-Aware Composite Scoring

Raw severity weights are summed, but the system also detects **correlated signal pairs** that are more suspicious together than individually:

| Correlated Pair | Bonus |
|---|---|
| `new_vendor` + `first_payment` | +15 |
| `new_vendor` + `high_amount_vs_average` | +20 |
| `velocity_spike` + `amount_statistical_outlier` | +20 |
| `category_mismatch` + `high_amount_vs_average` | +15 |
| `rapid_escalation` + `velocity_spike` | +20 |
| `weekend_large_amount` + `round_amount_large` | +10 |

Correlation bonuses are capped at 40 points total to prevent score inflation. The final composite score (raw + correlation bonus) is capped at 100.

### Vendor Context

The risk scoring module builds a `VendorContext` object attached to the risk report:

```
VendorContext:
  name: str              # Vendor display name
  age_days: int          # Days since vendor was created
  status: str            # ACTIVE or BLOCKED
  total_payments: int    # Lifetime payment count
  avg_amount: float      # Average payment amount (or null)
  dominant_category: str  # Most frequent payment category (or null)
  dominance_pct: float   # How dominant that category is (0-100%)
  recent_payments: list  # Last 5 payments: {amount, category, status, days_ago}
```

This structured profile is passed to the LLM so it can reason about whether a payment "fits" a vendor's established patterns.

### How Signals Adapt Over Time
- `new_vendor` — disappears after 7 days
- `first_payment` — disappears after the first successful payment
- `high_amount_vs_average` — shifts as more payments establish a baseline
- `amount_statistical_outlier` — only activates after 3+ payments (needs data for standard deviation)
- `velocity_spike` — compares current day to 30-day average (adapts to normal frequency)
- `category_mismatch` — only activates after 5+ payments with 70%+ category dominance
- `rapid_escalation` — only checks the last 3 payments
- `typo_squatting` — always-on (static name comparison)

The system naturally becomes less suspicious of vendors with consistent payment history, without any ML training or model retraining pipeline.

---

## LLM Agent Layer (Gemini)

Located in `backend/app/services/llm_client.py`.

### Model
**Gemini 2.5 Flash** — Google's fast, free-tier model. Chosen for:
- Free tier: 5 RPM, 250K TPM, 20 RPD
- Fast response (~2-3 seconds)
- Good at structured JSON output
- Thinking capability (internal reasoning before responding)

### System Prompt (Analysis Framework)
The system prompt defines a structured **4-dimension analysis framework**:

1. **Pattern Fit** — Does this payment fit the vendor's historical pattern (amount, category, frequency)?
2. **Signal Correlation** — Are multiple risk signals correlated (genuinely suspicious) or coincidental (normal variation)?
3. **Description Plausibility** — Does the description/category make sense for this vendor and amount?
4. **Human Review Heuristic** — Would a reasonable human reviewer want to see this before it goes through?

Rules are embedded in the prompt:
- Can only escalate (`should_escalate: true`) — never override BLOCK or downgrade REQUIRE_APPROVAL
- Be conservative: when uncertain, escalate
- Empty risk signals with a normal-looking payment should NOT be escalated

### User Prompt (Enriched Context)
The per-payment prompt sent to Gemini includes five sections:

1. **Payment Details** — amount, currency, category, description
2. **Policy Verdict** — engine verdict + list of triggered rules
3. **Risk Signals** — all triggered signals + composite score
4. **Vendor Profile** — name, age (days), status, total payments, average amount, dominant category with dominance percentage
5. **Recent Payment History** — last 5 payments with amount, category, status, and days ago

This enrichment allows Gemini to reason about context ("this is a 0-day-old vendor's first payment with a suspicious description") rather than just seeing raw numbers.

### Token Optimization
- `max_output_tokens: 1024` — enough for JSON response
- `thinking_budget: 128` — limits internal reasoning tokens
- `response_mime_type: "application/json"` — forces structured output
- `temperature: 0.2` — low creativity, high consistency

### Fault Tolerance
If Gemini is unavailable (API error, rate limit, timeout), the system falls back to `_DEFAULT_ASSESSMENT` with `should_escalate: false`. This means: if the AI breaks, payments continue to flow based on policy engine decisions alone. The AI is an enhancement, not a dependency.

### What Makes It "Agentic"
The LLM isn't just classifying — it's **reasoning about context**:
- It spots "Micros0ft" as a potential typo-squatting attack
- It flags "test payment" descriptions on large transactions as suspicious
- It correlates multiple moderate signals into a high-risk assessment
- It explains its reasoning in natural language (logged in audit trail)

This is qualitative analysis that deterministic rules can't do.

---

## Agent Orchestrator

Located in `backend/app/services/agent_orchestrator.py`.

The orchestrator is the **glue** that wires everything together:

1. Receives the payment + policy engine result
2. Calls risk scoring → gets 11 risk signals + composite score + `VendorContext`
3. Builds an enriched prompt with vendor profile, recent history, policy verdict, and signals
4. Calls Gemini → gets agent assessment (risk score, explanation, escalation flag, suspicious patterns, confidence)
5. Applies the decision rule (escalation only)
6. Returns the final verdict + all metadata for audit logging

### Why a Separate Orchestrator?
Separation of concerns:
- Policy engine doesn't know about the LLM
- LLM client doesn't know about policies
- Risk scoring doesn't know about either
- The orchestrator is the only place where the decision rule lives

This makes each component independently testable and replaceable.

---

## Guardrails

The system has three layers of guardrails:

### Layer 1: Code-Level (Policy Engine)
Hard limits that can't be bypassed:
- Spending caps (daily, monthly, per-transaction)
- Vendor blocklist
- Velocity limits
- Idempotency enforcement

### Layer 2: Architectural (Design Decisions)
Baked into how the system is wired:
- **BLOCK is absolute** — LLM is never even called on blocked payments
- **Escalation only** — LLM can make things stricter, never weaker
- **Human in the loop** — flagged payments require explicit human approval
- **Immutable audit trail** — decisions can't be edited or deleted

### Layer 3: Infrastructure (Operational)
- **Rate limiting** — 10 requests/minute per user on payment creation
- **JWT + RBAC** — only admins/approvers can approve payments
- **Stripe idempotency** — same key sent to Stripe prevents double-charging on retries
- **Celery retries with dead-letter** — failed executions are retried with exponential backoff

### Why Guardrails Matter
The AI is treated as an **advisor, not a decision-maker**. Even if Gemini hallucinates, gets prompt-injected, or returns garbage, the worst outcome is: the payment goes to human review. It can never accidentally approve something the policy engine blocked.

---

## Payment Execution Pipeline

### Async Execution via Celery
When a payment is approved (either auto-approved or manually approved), a Celery task is dispatched:

1. **Lock** — `SELECT ... FOR UPDATE` on the payment row (prevents double execution)
2. **Check idempotency** — if a successful transaction already exists for this payment, skip
3. **Update status** — set to `EXECUTING`
4. **Call payment provider** — Stripe `PaymentIntent.create()` with idempotency key
5. **Record transaction** — insert into transactions table with provider response
6. **Update status** — set to `COMPLETED` or `FAILED`
7. **Audit log** — record execution result

### Provider Abstraction
The `providers/` module defines an abstract `PaymentProvider` interface:
- `StripeProvider` — real Stripe API calls (test or live mode)
- `MockProvider` — fake success for local testing

Switch between them with `PAYMENT_PROVIDER=stripe` or `PAYMENT_PROVIDER=mock` in `.env`.

### Dual Idempotency
1. **Database level** — unique constraint on `idempotency_key` column prevents duplicate payment requests
2. **Stripe level** — the same idempotency key is passed to Stripe's API, so even if our Celery worker retries due to a crash, Stripe won't charge twice

### Retry Strategy
Celery tasks retry up to 3 times with exponential backoff (10s, 60s, 300s). After max retries, the payment is marked `FAILED` and logged as a dead-letter for manual investigation.

---

## Authentication & Authorization

### JWT Tokens
- **Access token** — 15 minutes, used for API calls
- **Refresh token** — 7 days, used to get new access tokens
- Tokens are signed with HS256

### Roles (RBAC)
| Role | Can Create Payments | Can Approve | Can Manage Policies |
|---|---|---|---|
| `admin` | Yes | Yes | Yes |
| `approver` | Yes | Yes | No |
| `operator` | Yes | No | No |

### Rate Limiting
- Per-user when authenticated (extracted from JWT)
- Per-IP when not authenticated
- Proxy-safe (reads `X-Forwarded-For`, `X-Real-IP`)
- 10 requests/minute on payment creation endpoint

---

## Data Model

### Core Tables

**users** — Authentication and RBAC
- `id`, `email`, `hashed_password`, `role`, `is_active`

**vendors** — Payment recipients
- `id`, `name`, `external_id`, `category`, `status` (ACTIVE/BLOCKED), `daily_limit`, `monthly_limit`

**policies** — Configurable business rules
- `id`, `name`, `rule_type`, `parameters` (JSONB), `priority`, `is_active`

**payment_requests** — The central entity
- `id`, `vendor_id`, `amount`, `currency`, `description`, `category`, `status`, `idempotency_key`, `created_by`
- Status flow: `PENDING` → `APPROVED` / `REQUIRE_APPROVAL` / `BLOCKED` → `EXECUTING` → `COMPLETED` / `FAILED`

**approval_requests** — Human review queue
- `id`, `payment_request_id`, `status` (PENDING/APPROVED/REJECTED), `decided_by`, `decided_at`, `reason`

**transactions** — Actual payment execution records
- `id`, `payment_request_id`, `provider`, `provider_txn_id`, `amount`, `currency`, `status`, `raw_response` (JSONB)

**audit_logs** — Immutable event trail
- `id`, `payment_request_id`, `event_type`, `actor`, `detail` (JSONB)
- Event types: `PAYMENT_EVALUATED`, `APPROVAL_DECIDED`, `PAYMENT_EXECUTED`

### Design Decisions
- **UUIDs** for all primary keys (no sequential IDs leaked)
- **Numeric(12,2)** for all money fields (no floating-point errors)
- **JSONB** for flexible data (policy parameters, audit details, provider responses)
- **server_default=text("now()")** for timestamps (DB clock, not app clock)

---

## Tech Stack Rationale

| Choice | Why |
|---|---|
| **FastAPI** | Async-native, auto-generated OpenAPI docs, Pydantic validation |
| **Neon DB** | Serverless PostgreSQL, free tier, zero DevOps, production-ready |
| **SQLAlchemy 2.0** | Async sessions for FastAPI, sync sessions for Celery (Celery is sync by nature) |
| **Redis** | Celery broker + rate limiting backend, fast, battle-tested |
| **Celery** | Mature async task queue with retries, dead-letter handling, scheduling |
| **Stripe** | Industry standard, excellent test mode, free sandbox |
| **Gemini 2.5 Flash** | Free tier, fast, good structured output, thinking capability |
| **Next.js 14** | App Router, server components, great DX |
| **Tailwind CSS v4** | Utility-first, fast iteration, no CSS files to manage |
| **TanStack Query** | Automatic caching, refetching, loading states for API data |

---

## Security Considerations

- **Passwords** hashed with bcrypt (direct, not passlib — avoids version conflicts)
- **JWT secrets** should be random 32+ character strings in production
- **Database credentials** stored in `.env`, never committed
- **Stripe keys** are test-mode (`sk_test_`) — switch to `sk_live_` for production
- **CORS** configured for localhost in development
- **SQL injection** prevented by SQLAlchemy parameterized queries
- **Rate limiting** prevents brute force and abuse
- **Idempotency** prevents double-charging at both DB and Stripe level

---

## What This Is Not

- **Not ML-based** — no trained models, no feature vectors, no model retraining pipeline. Risk detection is rule-based + LLM reasoning.
- **Not RAG** — no vector database, no document retrieval. All context is computed in real-time from structured DB queries and passed directly to the LLM.
- **Not multi-agent** — single LLM call per payment. No agent chains, no tool use, no iterative reasoning loops.
- **Not a payment gateway** — it orchestrates payment decisions and delegates execution to Stripe. It doesn't handle card numbers, PCI compliance, or settlement.

It is a **realistic production pattern** for intelligent payment processing: deterministic rules for compliance, LLM for qualitative risk analysis, humans for final authority on edge cases.
