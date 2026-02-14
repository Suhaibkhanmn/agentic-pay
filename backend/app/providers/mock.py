"""
Mock payment provider for local testing.

Rules:
  - amount < 10000  → success
  - amount >= 10000 → failure (simulates decline)

Accepts idempotency_key for interface consistency.
"""

import uuid
from decimal import Decimal
from typing import Optional

from app.providers.base import PaymentProvider, PaymentResult


class MockProvider(PaymentProvider):

    def create_payment(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> PaymentResult:
        txn_id = f"mock_{uuid.uuid4().hex[:12]}"

        if amount >= Decimal("10000"):
            return PaymentResult(
                success=False,
                provider_txn_id=txn_id,
                error_message="Mock decline: amount >= 10000",
                raw_response={
                    "id": txn_id,
                    "status": "declined",
                    "reason": "amount_too_high",
                },
            )

        return PaymentResult(
            success=True,
            provider_txn_id=txn_id,
            raw_response={
                "id": txn_id,
                "status": "succeeded",
                "amount": str(amount),
                "currency": currency,
                "idempotency_key": idempotency_key,
            },
        )

    def get_status(self, provider_txn_id: str) -> PaymentResult:
        # Mock always reports success for previously created txns
        return PaymentResult(
            success=True,
            provider_txn_id=provider_txn_id,
            raw_response={"id": provider_txn_id, "status": "succeeded"},
        )
