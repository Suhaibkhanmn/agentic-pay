import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RuleType(str, enum.Enum):
    MAX_TXN = "MAX_TXN"
    DAILY_CAP = "DAILY_CAP"
    MONTHLY_CAP = "MONTHLY_CAP"
    VELOCITY = "VELOCITY"
    CATEGORY_BUDGET = "CATEGORY_BUDGET"
    VENDOR_ALLOWLIST = "VENDOR_ALLOWLIST"
    APPROVAL_THRESHOLD = "APPROVAL_THRESHOLD"


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )
