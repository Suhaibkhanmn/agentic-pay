import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    payment_request_id: Optional[uuid.UUID]
    event_type: str
    actor: str
    detail: dict
    created_at: datetime

    model_config = {"from_attributes": True}
