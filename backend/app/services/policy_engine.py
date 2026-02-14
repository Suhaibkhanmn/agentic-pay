"""
Deterministic policy engine — hard guardrails for every payment request.

Every payment is evaluated against all active policies.  The MOST RESTRICTIVE
verdict wins:  BLOCK > REQUIRE_APPROVAL > ALLOW_AUTOPAY.

The agent layer (Phase 3) can only *escalate* from ALLOW_AUTOPAY to
REQUIRE_APPROVAL.  It can never override a BLOCK.
"""

import enum
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_request import PaymentRequest, PaymentStatus
from app.models.policy import Policy, RuleType
from app.models.transaction import Transaction, TransactionStatus
from app.models.vendor import Vendor, VendorStatus


# ── Verdict types ──────────────────────────────────────────────


class PolicyVerdict(str, enum.Enum):
    ALLOW_AUTOPAY = "ALLOW_AUTOPAY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"


# Ordering: higher = more restrictive
_SEVERITY = {
    PolicyVerdict.ALLOW_AUTOPAY: 0,
    PolicyVerdict.REQUIRE_APPROVAL: 1,
    PolicyVerdict.BLOCK: 2,
}


class TriggeredRule(BaseModel):
    rule_name: str
    rule_type: str
    verdict: str
    detail: str


class PolicyResult(BaseModel):
    verdict: PolicyVerdict
    triggered_rules: list[TriggeredRule]


# ── Main evaluator ─────────────────────────────────────────────


async def evaluate(
    payment: PaymentRequest,
    db: AsyncSession,
) -> PolicyResult:
    """
    Run all active policies against a payment request.
    Returns the most restrictive verdict + list of every triggered rule.
    """
    result = await db.execute(
        select(Policy)
        .where(Policy.is_active == True)  # noqa: E712
        .order_by(Policy.priority.desc())
    )
    policies = result.scalars().all()

    triggered: list[TriggeredRule] = []
    worst_verdict = PolicyVerdict.ALLOW_AUTOPAY

    for policy in policies:
        rule_fn = _RULE_DISPATCH.get(policy.rule_type)
        if rule_fn is None:
            continue

        rule_result = await rule_fn(payment, policy, db)
        if rule_result is not None:
            triggered.append(rule_result)
            candidate = PolicyVerdict(rule_result.verdict)
            if _SEVERITY[candidate] > _SEVERITY[worst_verdict]:
                worst_verdict = candidate

    # ── Idempotency check (always runs, not policy-table driven) ──
    idem = await _check_idempotency(payment, db)
    if idem is not None:
        triggered.append(idem)
        worst_verdict = PolicyVerdict.BLOCK

    return PolicyResult(verdict=worst_verdict, triggered_rules=triggered)


# ── Individual rule evaluators ─────────────────────────────────


async def _check_max_transaction(
    payment: PaymentRequest,
    policy: Policy,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """BLOCK if amount exceeds the per-transaction maximum."""
    max_amount = Decimal(str(policy.parameters.get("max_amount", 0)))
    if max_amount and payment.amount > max_amount:
        return TriggeredRule(
            rule_name=policy.name,
            rule_type=policy.rule_type,
            verdict=PolicyVerdict.BLOCK.value,
            detail=f"Amount {payment.amount} exceeds max {max_amount}",
        )
    return None


async def _check_daily_cap(
    payment: PaymentRequest,
    policy: Policy,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """BLOCK if today's total for this vendor would exceed the daily cap."""
    daily_cap = Decimal(str(policy.parameters.get("daily_cap", 0)))
    if not daily_cap:
        return None

    today_start = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
            PaymentRequest.vendor_id == payment.vendor_id,
            PaymentRequest.status.in_(
                [
                    PaymentStatus.APPROVED.value,
                    PaymentStatus.EXECUTING.value,
                    PaymentStatus.COMPLETED.value,
                ]
            ),
            PaymentRequest.created_at >= today_start,
            PaymentRequest.id != payment.id,  # exclude current
        )
    )
    today_total = result.scalar() or Decimal("0")

    if today_total + payment.amount > daily_cap:
        return TriggeredRule(
            rule_name=policy.name,
            rule_type=policy.rule_type,
            verdict=PolicyVerdict.BLOCK.value,
            detail=(
                f"Daily total would be {today_total + payment.amount}, "
                f"cap is {daily_cap}"
            ),
        )
    return None


async def _check_monthly_cap(
    payment: PaymentRequest,
    policy: Policy,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """BLOCK if this month's total for this vendor would exceed the cap."""
    monthly_cap = Decimal(str(policy.parameters.get("monthly_cap", 0)))
    if not monthly_cap:
        return None

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
            PaymentRequest.vendor_id == payment.vendor_id,
            PaymentRequest.status.in_(
                [
                    PaymentStatus.APPROVED.value,
                    PaymentStatus.EXECUTING.value,
                    PaymentStatus.COMPLETED.value,
                ]
            ),
            PaymentRequest.created_at >= month_start,
            PaymentRequest.id != payment.id,
        )
    )
    month_total = result.scalar() or Decimal("0")

    if month_total + payment.amount > monthly_cap:
        return TriggeredRule(
            rule_name=policy.name,
            rule_type=policy.rule_type,
            verdict=PolicyVerdict.BLOCK.value,
            detail=(
                f"Monthly total would be {month_total + payment.amount}, "
                f"cap is {monthly_cap}"
            ),
        )
    return None


async def _check_velocity(
    payment: PaymentRequest,
    policy: Policy,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """
    REQUIRE_APPROVAL if too many payments to this vendor in a short window.
    parameters: { "max_count": 5, "window_minutes": 60 }
    """
    max_count = policy.parameters.get("max_count", 5)
    window_minutes = policy.parameters.get("window_minutes", 60)

    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    result = await db.execute(
        select(func.count()).where(
            PaymentRequest.vendor_id == payment.vendor_id,
            PaymentRequest.created_at >= cutoff,
            PaymentRequest.id != payment.id,
        )
    )
    count = result.scalar() or 0

    if count >= max_count:
        return TriggeredRule(
            rule_name=policy.name,
            rule_type=policy.rule_type,
            verdict=PolicyVerdict.REQUIRE_APPROVAL.value,
            detail=(
                f"{count} payments in last {window_minutes}min "
                f"(limit {max_count})"
            ),
        )
    return None


async def _check_vendor_allowlist(
    payment: PaymentRequest,
    policy: Policy,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """BLOCK if vendor is not ACTIVE."""
    result = await db.execute(
        select(Vendor).where(Vendor.id == payment.vendor_id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor or vendor.status != VendorStatus.ACTIVE.value:
        return TriggeredRule(
            rule_name=policy.name,
            rule_type=policy.rule_type,
            verdict=PolicyVerdict.BLOCK.value,
            detail=f"Vendor {payment.vendor_id} is not active/allowed",
        )
    return None


async def _check_category_budget(
    payment: PaymentRequest,
    policy: Policy,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """
    BLOCK if adding this payment would exceed the monthly budget for
    the payment's category.
    parameters: { "category": "software", "monthly_budget": 10000 }
    """
    target_category = policy.parameters.get("category", "")
    monthly_budget = Decimal(str(policy.parameters.get("monthly_budget", 0)))

    if not target_category or not monthly_budget:
        return None
    if payment.category != target_category:
        return None

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
            PaymentRequest.category == target_category,
            PaymentRequest.status.in_(
                [
                    PaymentStatus.APPROVED.value,
                    PaymentStatus.EXECUTING.value,
                    PaymentStatus.COMPLETED.value,
                ]
            ),
            PaymentRequest.created_at >= month_start,
            PaymentRequest.id != payment.id,
        )
    )
    spent = result.scalar() or Decimal("0")

    if spent + payment.amount > monthly_budget:
        return TriggeredRule(
            rule_name=policy.name,
            rule_type=policy.rule_type,
            verdict=PolicyVerdict.BLOCK.value,
            detail=(
                f"Category '{target_category}' budget: spent {spent} + "
                f"{payment.amount} > {monthly_budget}"
            ),
        )
    return None


async def _check_approval_threshold(
    payment: PaymentRequest,
    policy: Policy,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """
    REQUIRE_APPROVAL if amount exceeds threshold.
    parameters: { "threshold": 1000 }
    """
    threshold = Decimal(str(policy.parameters.get("threshold", 0)))
    if threshold and payment.amount > threshold:
        return TriggeredRule(
            rule_name=policy.name,
            rule_type=policy.rule_type,
            verdict=PolicyVerdict.REQUIRE_APPROVAL.value,
            detail=f"Amount {payment.amount} exceeds approval threshold {threshold}",
        )
    return None


async def _check_idempotency(
    payment: PaymentRequest,
    db: AsyncSession,
) -> Optional[TriggeredRule]:
    """
    BLOCK if a payment with the same idempotency_key already exists
    (and it's not the current one being evaluated).
    """
    result = await db.execute(
        select(PaymentRequest).where(
            PaymentRequest.idempotency_key == payment.idempotency_key,
            PaymentRequest.id != payment.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return TriggeredRule(
            rule_name="idempotency_check",
            rule_type="IDEMPOTENCY",
            verdict=PolicyVerdict.BLOCK.value,
            detail=f"Duplicate idempotency_key: {payment.idempotency_key}",
        )
    return None


# ── Dispatch table ─────────────────────────────────────────────

_RULE_DISPATCH = {
    RuleType.MAX_TXN.value: _check_max_transaction,
    RuleType.DAILY_CAP.value: _check_daily_cap,
    RuleType.MONTHLY_CAP.value: _check_monthly_cap,
    RuleType.VELOCITY.value: _check_velocity,
    RuleType.VENDOR_ALLOWLIST.value: _check_vendor_allowlist,
    RuleType.CATEGORY_BUDGET.value: _check_category_budget,
    RuleType.APPROVAL_THRESHOLD.value: _check_approval_threshold,
}
