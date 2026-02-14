"""
Deterministic risk signals — computed before sending context to the LLM.

These feed into the agent's prompt so Gemini knows what red flags exist.
They do NOT override the policy engine; they're purely informational.

All stats are computed live from the payment_requests table — no extra
tables or cached aggregations.  Fine at demo scale; would need
materialized views or a stats table in production.
"""

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from statistics import mean, stdev, median

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_request import PaymentRequest, PaymentStatus
from app.models.vendor import Vendor


class RiskSignal(BaseModel):
    signal: str
    severity: str  # "low" | "medium" | "high"
    detail: str


class VendorContext(BaseModel):
    """Vendor profile + recent history — reused by the prompt builder."""
    name: str
    age_days: int
    status: str
    total_payments: int
    avg_amount: float | None
    dominant_category: str | None
    dominance_pct: float | None
    recent_payments: list[dict]  # [{amount, category, status, days_ago}]


class RiskReport(BaseModel):
    signals: list[RiskSignal]
    composite_score: int  # 0-100, higher = riskier
    vendor_context: VendorContext | None = None


# ── Correlation pairs ──────────────────────────────────────────
# When both signals co-occur, add a bonus to the composite score.
# Total correlation bonus is capped at +30 to prevent spam escalation.
CORRELATED_PAIRS: dict[tuple[str, str], int] = {
    ("new_vendor", "high_amount_vs_average"): 15,
    ("new_vendor", "first_payment"): 10,
    ("velocity_spike", "rapid_escalation"): 20,
    ("round_amount_large", "new_vendor"): 10,
    ("outside_business_hours", "velocity_spike"): 10,
    ("category_mismatch", "new_vendor"): 10,
    ("round_amount_large", "category_mismatch"): 8,
}

CORRELATION_CAP = 30


async def compute_risk_signals(
    payment: PaymentRequest,
    db: AsyncSession,
) -> RiskReport:
    """Gather all deterministic risk signals for a payment request."""
    signals: list[RiskSignal] = []
    vendor_ctx: VendorContext | None = None

    # ── Fetch vendor ──
    vendor_result = await db.execute(
        select(Vendor).where(Vendor.id == payment.vendor_id)
    )
    vendor = vendor_result.scalar_one_or_none()

    # ── Fetch prior completed/approved payments for this vendor ──
    prior_amounts: list[float] = []
    prior_count = 0
    prior_rows_full: list = []
    if vendor:
        prior_q = await db.execute(
            select(
                PaymentRequest.amount,
                PaymentRequest.category,
                PaymentRequest.status,
                PaymentRequest.created_at,
            ).where(
                PaymentRequest.vendor_id == payment.vendor_id,
                PaymentRequest.id != payment.id,
                PaymentRequest.status.in_(
                    [
                        PaymentStatus.APPROVED.value,
                        PaymentStatus.COMPLETED.value,
                    ]
                ),
            ).order_by(PaymentRequest.created_at.desc())
        )
        prior_rows_full = prior_q.all()
        prior_count = len(prior_rows_full)
        prior_amounts = [float(r.amount) for r in prior_rows_full]

    if vendor:
        age = datetime.utcnow() - vendor.created_at

        # ── 1. New vendor (created < 7 days ago) ──
        if age < timedelta(days=7):
            signals.append(
                RiskSignal(
                    signal="new_vendor",
                    severity="medium",
                    detail=f"Vendor '{vendor.name}' created {age.days} days ago",
                )
            )

        # ── 2. First payment to this vendor ──
        if prior_count == 0:
            signals.append(
                RiskSignal(
                    signal="first_payment",
                    severity="medium",
                    detail=f"First-ever payment to vendor '{vendor.name}'",
                )
            )

        # ── 3. Amount vs vendor average (2x, for small history) ──
        if 1 <= prior_count < 10:
            avg_amount = mean(prior_amounts)
            if avg_amount and float(payment.amount) > avg_amount * 2:
                signals.append(
                    RiskSignal(
                        signal="high_amount_vs_average",
                        severity="high",
                        detail=(
                            f"Amount {payment.amount} is >"
                            f" 2x vendor average ({avg_amount:.2f})"
                            f" (based on {prior_count} payments)"
                        ),
                    )
                )

        # ── 4. Statistical outlier (3σ, requires ≥10 history) ──
        if prior_count >= 10:
            avg_amount = mean(prior_amounts)
            std_amount = stdev(prior_amounts)
            threshold = avg_amount + 3 * std_amount
            if std_amount > 0 and float(payment.amount) > threshold:
                signals.append(
                    RiskSignal(
                        signal="amount_statistical_outlier",
                        severity="high",
                        detail=(
                            f"Amount {payment.amount} exceeds "
                            f"mean + 3σ ({threshold:.2f}) "
                            f"based on {prior_count} prior payments"
                        ),
                    )
                )

        # ── 5. Typo-squatting detection ──
        all_vendors_result = await db.execute(
            select(Vendor).where(Vendor.id != vendor.id)
        )
        all_vendors = all_vendors_result.scalars().all()
        for other in all_vendors:
            ratio = SequenceMatcher(
                None, vendor.name.lower(), other.name.lower()
            ).ratio()
            if 0.75 < ratio < 1.0:
                signals.append(
                    RiskSignal(
                        signal="typo_squatting",
                        severity="high",
                        detail=(
                            f"Vendor '{vendor.name}' is suspiciously similar "
                            f"to existing vendor '{other.name}' "
                            f"(similarity: {ratio:.0%})"
                        ),
                    )
                )

        # ── 6. Category mismatch (≥80% dominance in one category) ──
        if prior_count >= 3 and payment.category:
            cat_q = await db.execute(
                select(PaymentRequest.category).where(
                    PaymentRequest.vendor_id == payment.vendor_id,
                    PaymentRequest.id != payment.id,
                    PaymentRequest.category.isnot(None),
                )
            )
            all_cats = [r[0] for r in cat_q.all() if r[0]]
            if all_cats:
                from collections import Counter
                cat_counts = Counter(all_cats)
                top_cat, top_count = cat_counts.most_common(1)[0]
                dominance = top_count / len(all_cats)
                if dominance >= 0.8 and payment.category != top_cat:
                    signals.append(
                        RiskSignal(
                            signal="category_mismatch",
                            severity="medium",
                            detail=(
                                f"Vendor typically in '{top_cat}' "
                                f"({dominance:.0%} of payments), "
                                f"this payment is '{payment.category}'"
                            ),
                        )
                    )

        # ── 7. Rapid escalation (>5× median of last 5 completed) ──
        if prior_count >= 1:
            recent = prior_amounts[:5]  # already sorted desc by created_at
            baseline = median(recent) if len(recent) >= 2 else recent[0]
            if baseline > 0 and float(payment.amount) > baseline * 5:
                signals.append(
                    RiskSignal(
                        signal="rapid_escalation",
                        severity="high",
                        detail=(
                            f"Amount {payment.amount} is >"
                            f" 5x the median of last "
                            f"{len(recent)} payments ({baseline:.2f})"
                        ),
                    )
                )

    # ── 8. Velocity spike (≥3 payments to same vendor in 60 min) ──
    # Intentionally stricter than the VELOCITY policy rule.
    # Risk signal can escalate via agent even when policy allows.
    window = datetime.utcnow() - timedelta(minutes=60)
    vel_q = await db.execute(
        select(func.count()).where(
            PaymentRequest.vendor_id == payment.vendor_id,
            PaymentRequest.id != payment.id,
            PaymentRequest.created_at >= window,
        )
    )
    recent_count = vel_q.scalar() or 0
    if recent_count >= 3:
        signals.append(
            RiskSignal(
                signal="velocity_spike",
                severity="high",
                detail=(
                    f"{recent_count} other payments to this vendor "
                    f"in the last 60 minutes"
                ),
            )
        )

    # ── 9. Payment outside business hours (UTC 9-17 weekdays) ──
    now = datetime.utcnow()
    is_weekend = now.weekday() >= 5

    if is_weekend or now.hour < 9 or now.hour >= 17:
        signals.append(
            RiskSignal(
                signal="outside_business_hours",
                severity="low",
                detail=f"Payment submitted at {now.strftime('%A %H:%M UTC')}",
            )
        )

    # ── 10. Weekend + large amount ──
    if is_weekend and float(payment.amount) > 1000:
        signals.append(
            RiskSignal(
                signal="weekend_large_amount",
                severity="medium",
                detail=(
                    f"${payment.amount} submitted on "
                    f"{now.strftime('%A')} (weekend)"
                ),
            )
        )

    # ── 11. Round amount on large payments (low severity alone) ──
    amt = float(payment.amount)
    if amt >= 5000 and amt == int(amt):
        signals.append(
            RiskSignal(
                signal="round_amount_large",
                severity="low",
                detail=f"Large round amount: ${amt:,.0f}",
            )
        )

    # ── Composite score ──
    severity_weights = {"low": 10, "medium": 25, "high": 40}
    raw = sum(severity_weights.get(s.severity, 0) for s in signals)

    # Correlation bonus (capped at CORRELATION_CAP)
    fired_signals = {s.signal for s in signals}
    correlation_bonus = 0
    for (a, b), bonus in CORRELATED_PAIRS.items():
        if a in fired_signals and b in fired_signals:
            correlation_bonus += bonus
    correlation_bonus = min(correlation_bonus, CORRELATION_CAP)

    composite = min(raw + correlation_bonus, 100)

    # ── Build VendorContext for prompt enrichment ──
    if vendor:
        age = datetime.utcnow() - vendor.created_at
        avg_amt = mean(prior_amounts) if prior_amounts else None

        # Dominant category
        all_cats = [r.category for r in prior_rows_full if r.category]
        dom_cat = None
        dom_pct = None
        if all_cats:
            from collections import Counter
            cat_counts = Counter(all_cats)
            top_cat, top_count = cat_counts.most_common(1)[0]
            dom_cat = top_cat
            dom_pct = round(top_count / len(all_cats), 2)

        # Recent payments (last 5)
        now_ts = datetime.utcnow()
        recent = [
            {
                "amount": float(r.amount),
                "category": r.category or "n/a",
                "status": r.status,
                "days_ago": (now_ts - r.created_at).days,
            }
            for r in prior_rows_full[:5]
        ]

        vendor_ctx = VendorContext(
            name=vendor.name,
            age_days=age.days,
            status=vendor.status,
            total_payments=prior_count,
            avg_amount=round(avg_amt, 2) if avg_amt else None,
            dominant_category=dom_cat,
            dominance_pct=dom_pct,
            recent_payments=recent,
        )

    return RiskReport(
        signals=signals,
        composite_score=composite,
        vendor_context=vendor_ctx,
    )
