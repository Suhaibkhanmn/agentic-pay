import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from app.models.vendor import VendorStatus


class VendorCreate(BaseModel):
    name: str
    external_id: Optional[str] = None
    category: Optional[str] = None
    daily_limit: Optional[Decimal] = None
    monthly_limit: Optional[Decimal] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    external_id: Optional[str] = None
    category: Optional[str] = None
    status: Optional[VendorStatus] = None
    daily_limit: Optional[Decimal] = None
    monthly_limit: Optional[Decimal] = None


class VendorResponse(BaseModel):
    id: uuid.UUID
    name: str
    external_id: Optional[str]
    category: Optional[str]
    status: str
    daily_limit: Optional[Decimal]
    monthly_limit: Optional[Decimal]
    created_at: datetime

    model_config = {"from_attributes": True}
