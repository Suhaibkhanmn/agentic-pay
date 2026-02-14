"""Abstract payment provider interface."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class PaymentResult(BaseModel):
    success: bool
    provider_txn_id: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: dict = {}


class PaymentProvider(ABC):
    """
    All payment providers implement this interface.
    Implementations MUST be synchronous — they run inside Celery workers.
    """

    @abstractmethod
    def create_payment(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> PaymentResult:
        ...

    @abstractmethod
    def get_status(self, provider_txn_id: str) -> PaymentResult:
        ...
