"""
Stripe payment provider (test mode).

Passes the PaymentRequest's idempotency_key to Stripe so retries
at the Stripe level are also deduplicated.
"""

import logging
from decimal import Decimal
from typing import Optional

import stripe

from app.core.config import settings
from app.providers.base import PaymentProvider, PaymentResult

logger = logging.getLogger(__name__)


class StripeProvider(PaymentProvider):

    def __init__(self):
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def create_payment(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> PaymentResult:
        """
        Create and confirm a Stripe PaymentIntent in test mode.

        Stripe amounts are in smallest currency unit (cents for USD),
        so we multiply by 100.
        """
        try:
            amount_cents = int(amount * 100)

            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                description=description or "Agentic Payment",
                metadata=metadata or {},
                # Auto-confirm with test payment method
                confirm=True,
                payment_method="pm_card_visa",  # test mode card
                return_url="https://example.com/return",
                idempotency_key=idempotency_key,
            )

            succeeded = intent.status in ("succeeded", "requires_capture")

            return PaymentResult(
                success=succeeded,
                provider_txn_id=intent.id,
                error_message=None if succeeded else f"Status: {intent.status}",
                raw_response={
                    "id": intent.id,
                    "status": intent.status,
                    "amount": intent.amount,
                    "currency": intent.currency,
                },
            )

        except stripe.error.CardError as e:
            logger.warning("Stripe card error: %s", e.user_message)
            return PaymentResult(
                success=False,
                error_message=e.user_message,
                raw_response={"error": str(e)},
            )
        except stripe.error.IdempotencyError as e:
            # Idempotency key reused with different params — should not happen
            logger.error("Stripe idempotency error: %s", e)
            return PaymentResult(
                success=False,
                error_message=f"Idempotency conflict: {e}",
                raw_response={"error": str(e)},
            )
        except stripe.error.StripeError as e:
            logger.error("Stripe error: %s", e)
            return PaymentResult(
                success=False,
                error_message=str(e),
                raw_response={"error": str(e)},
            )

    def get_status(self, provider_txn_id: str) -> PaymentResult:
        try:
            intent = stripe.PaymentIntent.retrieve(provider_txn_id)
            succeeded = intent.status in ("succeeded", "requires_capture")
            return PaymentResult(
                success=succeeded,
                provider_txn_id=intent.id,
                raw_response={
                    "id": intent.id,
                    "status": intent.status,
                    "amount": intent.amount,
                },
            )
        except stripe.error.StripeError as e:
            return PaymentResult(
                success=False,
                error_message=str(e),
                raw_response={"error": str(e)},
            )
