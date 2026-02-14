import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.policy import RuleType


class PolicyCreate(BaseModel):
    name: str
    rule_type: RuleType
    parameters: dict
    priority: int = 0
    is_active: bool = True


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    parameters: Optional[dict] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class PolicyResponse(BaseModel):
    id: uuid.UUID
    name: str
    rule_type: str
    parameters: dict
    priority: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
