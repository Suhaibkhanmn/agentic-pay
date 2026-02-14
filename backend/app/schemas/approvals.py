import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ApprovalDecision(BaseModel):
    action: str  # "approve" | "reject"
    reason: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    payment_request_id: uuid.UUID
    assigned_to: Optional[uuid.UUID]
    status: str
    decided_by: Optional[uuid.UUID]
    decided_at: Optional[datetime]
    reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
