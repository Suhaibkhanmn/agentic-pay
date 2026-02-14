import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.audit_log import AuditLog
from app.models.payment_request import PaymentRequest, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.approvals import ApprovalDecision, ApprovalResponse

router = APIRouter()


@router.get("/pending", response_model=list[ApprovalResponse])
async def list_pending(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.APPROVER)),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status == ApprovalStatus.PENDING.value)
        .order_by(ApprovalRequest.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.ADMIN, UserRole.APPROVER)
    ),
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(
            status_code=400, detail="action must be 'approve' or 'reject'"
        )

    result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Approval already decided")

    # ── Update approval ──
    approval.status = (
        ApprovalStatus.APPROVED.value
        if body.action == "approve"
        else ApprovalStatus.REJECTED.value
    )
    approval.decided_by = current_user.id
    approval.decided_at = datetime.utcnow()
    approval.reason = body.reason

    # ── Update parent payment request ──
    pr_result = await db.execute(
        select(PaymentRequest).where(
            PaymentRequest.id == approval.payment_request_id
        )
    )
    payment = pr_result.scalar_one()
    payment.status = (
        PaymentStatus.APPROVED.value
        if body.action == "approve"
        else PaymentStatus.REJECTED.value
    )

    # ── Audit log ──
    audit = AuditLog(
        payment_request_id=payment.id,
        event_type="APPROVAL_DECIDED",
        actor=f"user:{current_user.id}",
        detail={
            "action": body.action,
            "reason": body.reason,
            "decided_by": str(current_user.id),
        },
    )
    db.add(audit)

    await db.commit()
    await db.refresh(approval)

    # ── Dispatch Celery task if approved ──
    if body.action == "approve":
        try:
            from app.workers.dispatch import send_execute_payment

            send_execute_payment(str(payment.id))
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Celery dispatch failed (broker down?): %s — payment %s saved, "
                "will need manual retry.",
                exc,
                payment.id,
            )

    return approval
