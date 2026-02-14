import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class PaymentRequestCreate(BaseModel):
    vendor_id: uuid.UUID
    amount: Decimal
    currency: str = "USD"
    description: Optional[str] = None
    invoice_ref: Optional[str] = None
    category: Optional[str] = None
    idempotency_key: str


class PaymentRequestResponse(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    amount: Decimal
    currency: str
    description: Optional[str]
    invoice_ref: Optional[str]
    category: Optional[str]
    status: str
    idempotency_key: str
    created_by: Optional[uuid.UUID]
    created_at: datetime
    # Enriched fields (set by the processing pipeline)
    policy_result: Optional[dict] = None
    agent_reasoning: Optional[dict] = None

    model_config = {"from_attributes": True}


class PaymentListParams(BaseModel):
    status: Optional[str] = None
    vendor_id: Optional[uuid.UUID] = None
    limit: int = 50
    offset: int = 0
