"""
Celery tasks — run payment execution asynchronously.

IMPORTANT: These tasks use SYNC DB sessions (not async).
Celery workers are sync by nature; async DB here adds complexity for no benefit.
"""

import logging
import uuid

from celery import shared_task
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.payment_request import PaymentRequest, PaymentStatus
from app.models.transaction import Transaction, TransactionStatus
from app.providers.base import PaymentProvider

logger = logging.getLogger(__name__)


def _get_provider() -> PaymentProvider:
    """Resolve payment provider from config."""
    if settings.PAYMENT_PROVIDER == "stripe":
        from app.providers.stripe_provider import StripeProvider
        return StripeProvider()
    else:
        from app.providers.mock import MockProvider
        return MockProvider()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,  # seconds; exponential backoff below
    acks_late=True,
)
def execute_payment(self, payment_request_id: str) -> dict:
    """
    Execute payment for an approved PaymentRequest.

    Idempotency is enforced at TWO levels:
      1. DB level — check if a successful Transaction already exists
      2. Stripe level — pass idempotency_key so Stripe deduplicates
    """
    session = SyncSessionLocal()
    try:
        pr_id = uuid.UUID(payment_request_id)

        # ── Lock the payment request (SELECT FOR UPDATE) ──
        payment = session.execute(
            select(PaymentRequest)
            .where(PaymentRequest.id == pr_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not payment:
            logger.error("PaymentRequest %s not found", pr_id)
            return {"status": "error", "detail": "not_found"}

        if payment.status not in (
            PaymentStatus.APPROVED.value,
            PaymentStatus.EXECUTING.value,
        ):
            logger.info(
                "PaymentRequest %s status is %s — skipping",
                pr_id, payment.status,
            )
            return {"status": "skipped", "detail": payment.status}

        # ── DB idempotency: check for existing successful transaction ──
        existing_txn = session.execute(
            select(Transaction).where(
                Transaction.payment_request_id == pr_id,
                Transaction.status == TransactionStatus.SUCCESS.value,
            )
        ).scalar_one_or_none()

        if existing_txn:
            logger.info(
                "PaymentRequest %s already has successful txn %s — skipping",
                pr_id, existing_txn.provider_txn_id,
            )
            return {
                "status": "already_completed",
                "txn_id": str(existing_txn.id),
            }

        # ── Mark as executing ──
        payment.status = PaymentStatus.EXECUTING.value
        session.commit()

        # ── Execute payment via provider ──
        provider = _get_provider()
        result = provider.create_payment(
            amount=payment.amount,
            currency=payment.currency,
            idempotency_key=payment.idempotency_key,
            description=payment.description,
            metadata={"payment_request_id": str(pr_id)},
        )

        # ── Record transaction ──
        txn = Transaction(
            payment_request_id=pr_id,
            provider=settings.PAYMENT_PROVIDER.upper(),
            provider_txn_id=result.provider_txn_id,
            amount=payment.amount,
            currency=payment.currency,
            status=(
                TransactionStatus.SUCCESS.value
                if result.success
                else TransactionStatus.FAILED.value
            ),
            raw_response=result.raw_response,
        )
        session.add(txn)

        # ── Update payment status ──
        if result.success:
            payment.status = PaymentStatus.COMPLETED.value
        else:
            payment.status = PaymentStatus.FAILED.value

        # ── Audit log ──
        audit = AuditLog(
            payment_request_id=pr_id,
            event_type="PAYMENT_EXECUTED",
            actor="system:celery",
            detail={
                "provider": settings.PAYMENT_PROVIDER,
                "success": result.success,
                "provider_txn_id": result.provider_txn_id,
                "error_message": result.error_message,
            },
        )
        session.add(audit)
        session.commit()

        logger.info(
            "PaymentRequest %s → %s (txn: %s)",
            pr_id,
            "COMPLETED" if result.success else "FAILED",
            result.provider_txn_id,
        )

        # ── Retry on failure if retries remain ──
        if not result.success and self.request.retries < self.max_retries:
            raise self.retry(
                exc=Exception(result.error_message),
                countdown=10 * (2 ** self.request.retries),  # exponential backoff
            )

        return {
            "status": "completed" if result.success else "failed",
            "provider_txn_id": result.provider_txn_id,
        }

    except self.MaxRetriesExceededError:
        # ── Dead letter: all retries exhausted ──
        logger.error("PaymentRequest %s — max retries exceeded", payment_request_id)
        _mark_failed(session, uuid.UUID(payment_request_id))
        return {"status": "dead_letter", "detail": "max_retries_exceeded"}

    except Exception as e:
        session.rollback()
        logger.exception("Unexpected error executing payment %s", payment_request_id)
        # Retry with exponential backoff
        raise self.retry(
            exc=e,
            countdown=10 * (2 ** self.request.retries),
        )

    finally:
        session.close()


def _mark_failed(session, pr_id: uuid.UUID) -> None:
    """Mark a payment as failed after all retries exhausted."""
    try:
        payment = session.execute(
            select(PaymentRequest).where(PaymentRequest.id == pr_id)
        ).scalar_one_or_none()

        if payment:
            payment.status = PaymentStatus.FAILED.value
            audit = AuditLog(
                payment_request_id=pr_id,
                event_type="PAYMENT_DEAD_LETTER",
                actor="system:celery",
                detail={"reason": "max_retries_exceeded"},
            )
            session.add(audit)
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to mark payment %s as dead letter", pr_id)
