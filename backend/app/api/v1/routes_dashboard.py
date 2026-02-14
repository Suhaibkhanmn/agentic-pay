"""Dashboard aggregate stats — single endpoint for the overview page.

All timestamps are UTC.  Neon stores in UTC by default, and the
risk_scoring "business hours" check is also UTC-based.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.payment_request import PaymentRequest, PaymentStatus
from app.models.user import User

router = APIRouter()


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Only COMPLETED = actual money moved (not APPROVED/EXECUTING which
    # haven't been charged yet, and not FAILED which didn't go through).
    spend_statuses = [PaymentStatus.COMPLETED.value]

    # ── Spend today (UTC) ──
    r = await db.execute(
        select(func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
            PaymentRequest.status.in_(spend_statuses),
            PaymentRequest.created_at >= today_start,
        )
    )
    spend_today = float(r.scalar())

    # ── Spend this month (UTC) ──
    r = await db.execute(
        select(func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
            PaymentRequest.status.in_(spend_statuses),
            PaymentRequest.created_at >= month_start,
        )
    )
    spend_month = float(r.scalar())

    # ── Pending approvals ──
    r = await db.execute(
        select(func.count()).where(
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
    )
    pending_approvals = r.scalar()

    # ── Blocked count (this month) ──
    r = await db.execute(
        select(func.count()).where(
            PaymentRequest.status == PaymentStatus.BLOCKED.value,
            PaymentRequest.created_at >= month_start,
        )
    )
    blocked_count = r.scalar()

    # ── Completed count (this month) ──
    r = await db.execute(
        select(func.count()).where(
            PaymentRequest.status == PaymentStatus.COMPLETED.value,
            PaymentRequest.created_at >= month_start,
        )
    )
    completed_count = r.scalar()

    # ── Total payments today ──
    r = await db.execute(
        select(func.count()).where(
            PaymentRequest.created_at >= today_start,
        )
    )
    payments_today = r.scalar()

    # ── Daily spend for last 7 days (for chart, UTC) ──
    daily_spend = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        r = await db.execute(
            select(func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
                PaymentRequest.status.in_(spend_statuses),
                PaymentRequest.created_at >= day_start,
                PaymentRequest.created_at < day_end,
            )
        )
        daily_spend.append(
            {
                "date": day_start.strftime("%b %d"),
                "amount": float(r.scalar()),
            }
        )

    return {
        "spend_today": spend_today,
        "spend_month": spend_month,
        "pending_approvals": pending_approvals,
        "blocked_count": blocked_count,
        "completed_count": completed_count,
        "payments_today": payments_today,
        "daily_spend": daily_spend,
        "timezone": "UTC",  # explicit for frontend labels
    }
