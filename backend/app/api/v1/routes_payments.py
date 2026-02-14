import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.approval import ApprovalRequest
from app.models.audit_log import AuditLog
from app.models.payment_request import PaymentRequest, PaymentStatus
from app.models.user import User
from app.models.vendor import Vendor, VendorStatus
from app.schemas.payments import PaymentRequestCreate, PaymentRequestResponse
from app.services.agent_orchestrator import run as run_orchestrator
from app.services.policy_engine import evaluate

router = APIRouter()


@router.post("/", response_model=PaymentRequestResponse, status_code=201)
@limiter.limit("10/minute")
async def create_payment(
    request: Request,
    body: PaymentRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── 1. Validate vendor ──
    result = await db.execute(select(Vendor).where(Vendor.id == body.vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if vendor.status == VendorStatus.BLOCKED.value:
        raise HTTPException(status_code=400, detail="Vendor is blocked")

    # ── 2. Create payment request ──
    payment = PaymentRequest(
        vendor_id=body.vendor_id,
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        invoice_ref=body.invoice_ref,
        category=body.category,
        idempotency_key=body.idempotency_key,
        created_by=current_user.id,
    )
    db.add(payment)
    try:
        await db.flush()  # get the id before evaluation
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Payment with idempotency_key '{body.idempotency_key}' already exists.",
        )

    # ── 3. Policy engine ──
    policy_result = await evaluate(payment, db)

    # ── 4. Agent orchestrator (policy + LLM + risk scoring) ──
    orch_result = await run_orchestrator(payment, policy_result, db)

    # ── 5. Set final status from orchestrator ──
    payment.status = orch_result.final_status

    # ── 6. Create ApprovalRequest if needed ──
    if payment.status == PaymentStatus.REQUIRE_APPROVAL.value:
        approval = ApprovalRequest(payment_request_id=payment.id)
        db.add(approval)

    # ── 7. Audit log ──
    audit = AuditLog(
        payment_request_id=payment.id,
        event_type="PAYMENT_EVALUATED",
        actor="system",
        detail={
            "policy_verdict": orch_result.policy_verdict,
            "final_verdict": orch_result.final_verdict,
            "escalated_by_agent": orch_result.escalated_by_agent,
            "triggered_rules": [
                r.model_dump() for r in policy_result.triggered_rules
            ],
            "agent_assessment": orch_result.agent_assessment.model_dump(),
            "risk_signals": [
                s.model_dump() for s in orch_result.risk_report.signals
            ],
            "risk_composite_score": orch_result.risk_report.composite_score,
        },
    )
    db.add(audit)

    await db.commit()
    await db.refresh(payment)

    # ── 8. Dispatch Celery task if auto-approved ──
    if payment.status == PaymentStatus.APPROVED.value:
        try:
            from app.workers.dispatch import send_execute_payment

            send_execute_payment(str(payment.id))
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Celery dispatch failed (broker down?): %s — payment %s saved, "
                "will need manual retry or Celery catch-up.",
                exc,
                payment.id,
            )

    # ── 9. Build response ──
    resp = PaymentRequestResponse.model_validate(payment)
    resp.policy_result = {
        "verdict": orch_result.policy_verdict,
        "final_verdict": orch_result.final_verdict,
        "escalated_by_agent": orch_result.escalated_by_agent,
        "triggered_rules": [
            r.model_dump() for r in policy_result.triggered_rules
        ],
    }
    resp.agent_reasoning = orch_result.agent_assessment.model_dump()
    return resp


@router.get("/", response_model=list[PaymentRequestResponse])
async def list_payments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    vendor_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(PaymentRequest).order_by(PaymentRequest.created_at.desc())

    if status:
        query = query.where(PaymentRequest.status == status)
    if vendor_id:
        query = query.where(PaymentRequest.vendor_id == vendor_id)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{payment_id}", response_model=PaymentRequestResponse)
async def get_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PaymentRequest).where(PaymentRequest.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")
    return payment
