"""
Agent Orchestrator — combines risk scoring + Gemini LLM + policy engine.

EXPLICIT DECISION RULE (agent can only escalate, never downgrade):
  Policy = BLOCK              → final = BLOCK (agent IGNORED)
  Policy = REQUIRE_APPROVAL   → final = REQUIRE_APPROVAL (agent cannot downgrade)
  Policy = ALLOW_AUTOPAY + agent.should_escalate = true
                              → final = REQUIRE_APPROVAL (agent escalates)
  Policy = ALLOW_AUTOPAY + agent.should_escalate = false
                              → final = ALLOW_AUTOPAY (both agree)
"""

import logging
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_request import PaymentRequest, PaymentStatus
from app.services.llm_client import AgentAssessment, analyze
from app.services.policy_engine import PolicyResult, PolicyVerdict
from app.services.risk_scoring import RiskReport, VendorContext, compute_risk_signals

logger = logging.getLogger(__name__)


class OrchestratorResult(BaseModel):
    """Full result of the orchestration pipeline."""

    policy_verdict: str
    final_verdict: str
    final_status: str  # maps to PaymentStatus value
    agent_assessment: AgentAssessment
    risk_report: RiskReport
    escalated_by_agent: bool


async def run(
    payment: PaymentRequest,
    policy_result: PolicyResult,
    db: AsyncSession,
) -> OrchestratorResult:
    """
    Run the full decision pipeline:
    1. Compute deterministic risk signals (+ vendor context)
    2. Call Gemini LLM with enriched prompt (skip if BLOCK)
    3. Apply the escalation-only decision rule
    """

    # ── 1. Deterministic risk signals ──
    risk_report = await compute_risk_signals(payment, db)

    # ── 2. Agent reasoning (skip if BLOCK) ──
    if policy_result.verdict == PolicyVerdict.BLOCK:
        # Agent is ignored on BLOCK — still log a default for audit trail
        from app.services.llm_client import _DEFAULT_ASSESSMENT

        return OrchestratorResult(
            policy_verdict=policy_result.verdict.value,
            final_verdict=PolicyVerdict.BLOCK.value,
            final_status=PaymentStatus.BLOCKED.value,
            agent_assessment=_DEFAULT_ASSESSMENT,
            risk_report=risk_report,
            escalated_by_agent=False,
        )

    # Build enriched prompt with vendor context
    prompt = _build_prompt(payment, policy_result, risk_report)
    agent_assessment = await analyze(prompt)

    # ── 3. Apply decision rule ──
    escalated = False

    if policy_result.verdict == PolicyVerdict.REQUIRE_APPROVAL:
        # Agent cannot downgrade — stays REQUIRE_APPROVAL
        final_verdict = PolicyVerdict.REQUIRE_APPROVAL
        final_status = PaymentStatus.REQUIRE_APPROVAL.value

    elif policy_result.verdict == PolicyVerdict.ALLOW_AUTOPAY:
        if agent_assessment.should_escalate:
            # Agent escalates
            final_verdict = PolicyVerdict.REQUIRE_APPROVAL
            final_status = PaymentStatus.REQUIRE_APPROVAL.value
            escalated = True
            logger.info(
                "Agent escalated payment %s: %s",
                payment.id,
                agent_assessment.risk_explanation,
            )
        else:
            # Both agree — auto-pay
            final_verdict = PolicyVerdict.ALLOW_AUTOPAY
            final_status = PaymentStatus.APPROVED.value
    else:
        # Fallback safety — treat unknown as BLOCK
        final_verdict = PolicyVerdict.BLOCK
        final_status = PaymentStatus.BLOCKED.value

    return OrchestratorResult(
        policy_verdict=policy_result.verdict.value,
        final_verdict=final_verdict.value,
        final_status=final_status,
        agent_assessment=agent_assessment,
        risk_report=risk_report,
        escalated_by_agent=escalated,
    )


def _build_prompt(
    payment: PaymentRequest,
    policy_result: PolicyResult,
    risk_report: RiskReport,
) -> str:
    """Assemble an enriched context prompt for Gemini."""

    # ── Payment details ──
    lines = [
        "PAYMENT:",
        f"  Amount: {payment.amount} {payment.currency}",
        f"  Category: {payment.category or 'n/a'}",
        f"  Description: {payment.description or 'n/a'}",
    ]

    # ── Vendor profile (from VendorContext) ──
    vc = risk_report.vendor_context
    if vc:
        lines.append("")
        lines.append(f"VENDOR PROFILE ({vc.name}):")
        lines.append(f"  Age: {vc.age_days} days | Status: {vc.status}")
        lines.append(
            f"  Completed payments: {vc.total_payments}"
            + (f" | Average: ${vc.avg_amount:,.2f}" if vc.avg_amount else "")
        )
        if vc.dominant_category:
            lines.append(
                f"  Typical category: {vc.dominant_category} "
                f"({vc.dominance_pct:.0%} of payments)"
            )

        # ── Recent payment history ──
        if vc.recent_payments:
            lines.append("")
            lines.append(f"RECENT HISTORY (last {len(vc.recent_payments)}):")
            for rp in vc.recent_payments:
                lines.append(
                    f"  ${rp['amount']:,.2f} — {rp['category']} — "
                    f"{rp['status']} — {rp['days_ago']}d ago"
                )

    # ── Policy verdict + triggered rules ──
    lines.append("")
    lines.append(f"POLICY VERDICT: {policy_result.verdict.value}")

    triggered_rules_text = "\n".join(
        f"  - {r.rule_name} ({r.rule_type}): {r.detail} → {r.verdict}"
        for r in policy_result.triggered_rules
    )
    lines.append(
        f"TRIGGERED RULES:\n{triggered_rules_text or '  (none)'}"
    )

    # ── Risk signals ──
    lines.append("")
    risk_signals_text = "\n".join(
        f"  - [{s.severity.upper()}] {s.signal}: {s.detail}"
        for s in risk_report.signals
    )
    lines.append(
        f"RISK SIGNALS (composite: {risk_report.composite_score}/100):\n"
        f"{risk_signals_text or '  (none detected)'}"
    )

    lines.append("")
    lines.append("Analyze this payment. Return JSON assessment.")

    return "\n".join(lines)
