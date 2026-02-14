# Agentic Payments Orchestrator

An intelligent payment processing system that combines **deterministic policy rules** with **LLM-powered risk analysis** (Google Gemini) to make autonomous payment decisions — with human oversight for high-risk transactions.

Every payment flows through a three-layer decision pipeline: hard-coded business rules, 11 deterministic risk signals with correlation-aware scoring, and an AI reasoning layer that can escalate (but never override) decisions. The result is a system where low-risk payments auto-execute in seconds, suspicious ones get flagged for human review, and policy violations are blocked outright — with every decision traced in an immutable audit trail.

---

## How It Works

```
Payment Request
      │
      ▼
┌──────────────┐     7 configurable rules:
│ Policy Engine│───► MAX_TXN, DAILY_CAP, MONTHLY_CAP,
│ (hard rules) │     VELOCITY, VENDOR_ALLOWLIST,
└──────┬───────┘     CATEGORY_BUDGET, APPROVAL_THRESHOLD
       │
       ▼
┌──────────────┐     11 signals with correlation scoring:
│ Risk Scoring │───► new_vendor, first_payment, high_amount,
│ (signals)    │     typo_squatting, off_hours, statistical_outlier,
└──────┬───────┘     velocity_spike, round_amount, category_mismatch,
       │             weekend_large, rapid_escalation
       ▼
┌──────────────┐     Vendor profile + payment history enrichment
│  Gemini LLM  │───► 4-dimension analysis framework
│ (reasoning)  │     Pattern fit / Signal correlation /
└──────┬───────┘     Description plausibility / Human review heuristic
       │
       ▼
┌──────────────┐
│ Orchestrator │───► Applies escalation-only rule
└──────┬───────┘     AI can escalate, never downgrade
       │
  ┌────┼────────┐
  ▼    ▼        ▼
BLOCK  REVIEW  AUTO-PAY
       │        │
       ▼        ▼
    Approval  Celery ──► Stripe (test mode)
    Queue     Worker     with idempotency
       │        │
       └────────┘
            │
       Audit Trail
```

### The Decision Rule

| Policy Engine Says | Gemini Escalates? | Final Decision |
|---|---|---|
| **BLOCK** | *(never called)* | **BLOCKED** |
| REQUIRE_APPROVAL | *(irrelevant)* | **REQUIRE_APPROVAL** |
| ALLOW_AUTOPAY | Yes | **REQUIRE_APPROVAL** (escalated by AI) |
| ALLOW_AUTOPAY | No | **APPROVED** (auto-executed) |

The AI is an **advisor, not a decision-maker**. Even if Gemini hallucinates or gets prompt-injected, the worst outcome is a payment going to human review — it can never approve something the policy engine blocked.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API** | FastAPI (Python) | Async REST API with auto-generated OpenAPI docs |
| **Database** | PostgreSQL (Neon DB) | Serverless, free tier, zero DevOps |
| **ORM** | SQLAlchemy 2.0 | Async sessions for FastAPI, sync for Celery |
| **Migrations** | Alembic | Version-controlled schema changes |
| **Task Queue** | Celery + Redis | Async payment execution with retries |
| **AI** | Google Gemini 2.5 Flash | Risk reasoning with structured JSON output |
| **Payments** | Stripe (test mode) | PaymentIntent creation with idempotency |
| **Auth** | JWT (HS256) | Access + refresh tokens, RBAC |
| **Rate Limiting** | SlowAPI + Redis | Per-user + per-IP, proxy-safe |
| **Frontend** | Next.js 14 (App Router) | React dashboard with Tailwind CSS v4 |
| **Data Fetching** | TanStack React Query | Caching, refetching, loading states |
| **Charts** | Recharts | Dashboard visualizations |

---

## Project Structure

```
agentic-payment/
├── backend/
│   ├── app/
│   │   ├── api/v1/              # REST endpoints
│   │   │   ├── routes_auth.py       # Register, login, refresh, me
│   │   │   ├── routes_payments.py   # Submit + list payments
│   │   │   ├── routes_approvals.py  # Approval queue + decide
│   │   │   ├── routes_vendors.py    # Vendor CRUD
│   │   │   ├── routes_policies.py   # Policy CRUD
│   │   │   ├── routes_audit.py      # Audit log
│   │   │   └── routes_dashboard.py  # Stats + charts
│   │   ├── core/                # Config, security, rate limiting, logging
│   │   ├── db/                  # Session management + base model
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # Business logic
│   │   │   ├── policy_engine.py     # 7 deterministic rule evaluators
│   │   │   ├── risk_scoring.py      # 11 risk signals + correlation scoring
│   │   │   ├── llm_client.py        # Gemini integration + prompt design
│   │   │   └── agent_orchestrator.py# Wires policy + risk + LLM together
│   │   ├── providers/           # Payment provider abstraction
│   │   │   ├── base.py              # Abstract interface
│   │   │   ├── stripe_provider.py   # Real Stripe API calls
│   │   │   └── mock_provider.py     # Fake success for local testing
│   │   └── workers/             # Celery app, tasks, dispatch helper
│   ├── alembic/                 # Database migration scripts
│   ├── seed.py                  # Demo data seeder
│   ├── requirements.txt
│   ├── docker-compose.yml       # Redis + Celery worker + Celery beat
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── app/                     # Next.js pages
│   │   ├── dashboard/               # Stats, charts, spend overview
│   │   ├── payments/                # Submit + list + detail view
│   │   ├── approvals/               # Approval queue with inline reasoning
│   │   ├── audit/                   # Expandable audit log + copy JSON
│   │   ├── vendors/                 # Vendor management
│   │   ├── policies/                # Policy management
│   │   └── login/                   # Authentication
│   ├── components/              # Shared UI (layout, sidebar, cards)
│   └── lib/                     # API client, auth context, utilities
├── ARCHITECTURE.md              # Deep-dive: design, flow, guardrails
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker Desktop (for Redis)
- [Neon DB](https://neon.tech) account (free tier)
- [Google AI Studio](https://aistudio.google.com) API key (free tier)
- [Stripe](https://dashboard.stripe.com/test/apikeys) account (test mode, free)

### 1. Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment — copy and fill in your credentials
cp .env.example .env
```

Edit `.env` with your actual values:

| Variable | Where to Get It |
|---|---|
| `DATABASE_URL` | Neon console → Connection Details → select "asyncpg" driver |
| `SYNC_DATABASE_URL` | Same Neon connection string but with `psycopg2` driver |
| `REDIS_URL` | Default: `redis://127.0.0.1:6379/0` (local Docker) |
| `SECRET_KEY` | Any random string, 32+ characters (e.g. `openssl rand -hex 32`) |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) → Create API Key |
| `STRIPE_SECRET_KEY` | [Stripe Dashboard](https://dashboard.stripe.com/test/apikeys) → Secret key (`sk_test_...`) |
| `PAYMENT_PROVIDER` | `stripe` for real Stripe calls, `mock` for local testing |

```bash
# Start Redis (requires Docker Desktop running)
docker compose up -d redis

# Run database migrations
alembic upgrade head

# Seed demo data (3 vendors, 5 policies, sample payments)
python seed.py

# Start Celery worker (separate terminal, venv activated)
celery -A app.workers.celery_app worker --loglevel=info --pool=solo

# Start API server
uvicorn app.main:app --reload
```

### 2. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure API URL
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1" > .env.local

# Start dev server
npm run dev
```

### 3. Access

| Resource | URL |
|---|---|
| API Docs (Swagger) | http://localhost:8000/docs |
| Admin Dashboard | http://localhost:3000 |
| Demo Login | `admin@agentpay.dev` / `admin123` |

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login (JSON or form data) |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Current user info |

### Payments
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/payments/` | Submit payment request (triggers full decision pipeline) |
| GET | `/api/v1/payments/` | List all payments |
| GET | `/api/v1/payments/{id}` | Payment detail with agent reasoning |

### Approvals
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/approvals/pending` | Pending approval queue |
| POST | `/api/v1/approvals/{id}/decide` | Approve or reject with reason |

### Admin
| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/v1/vendors/` | List / create vendors |
| GET/POST | `/api/v1/policies/` | List / create policies |
| GET | `/api/v1/audit/` | Immutable audit log |
| GET | `/api/v1/dashboard/stats` | Dashboard statistics |

---

## Intelligence Layer

### Policy Engine (Deterministic Rules)
Seven configurable rule types evaluated on every payment. Most restrictive verdict wins. Rules are database rows — create, modify, and deactivate via API without code changes.

### Risk Scoring (11 Signals + Correlation)
Deterministic signals computed from database state. Includes **correlation-aware scoring** — co-occurring signals (e.g., `new_vendor` + `first_payment`) receive a bonus multiplier because their combination is more suspicious than either alone. Each signal fades naturally as vendors build payment history.

### LLM Agent (Gemini 2.5 Flash)
Receives the full context: payment details, **vendor profile** (age, total payments, average amount, dominant category), **recent payment history**, policy verdict, and all risk signals. Analyzes across four dimensions: pattern fit, signal correlation, description plausibility, and human review heuristic.

If Gemini is unavailable (API error, rate limit), the system gracefully falls back to policy engine decisions alone — AI is an enhancement, not a dependency.

### Vendor Context Enrichment
The prompt sent to Gemini includes a structured vendor profile built from historical data, enabling the model to reason about whether a payment "fits" a vendor's established patterns — not just whether it violates a static rule.

---

## Architecture

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for a comprehensive deep-dive covering:
- Decision flow (step-by-step)
- Policy engine rule types and evaluation strategy
- Risk signal definitions and adaptation over time
- LLM prompt design and token optimization
- Three-layer guardrail system
- Payment execution pipeline with dual idempotency
- Data model design decisions
- Security considerations
