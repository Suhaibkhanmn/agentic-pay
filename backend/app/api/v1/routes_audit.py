import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogResponse

router = APIRouter()


@router.get("/", response_model=list[AuditLogResponse])
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    payment_request_id: Optional[uuid.UUID] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())

    if payment_request_id:
        query = query.where(AuditLog.payment_request_id == payment_request_id)
    if event_type:
        query = query.where(AuditLog.event_type == event_type)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
