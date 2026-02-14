import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorResponse, VendorUpdate

router = APIRouter()


@router.post("/", response_model=VendorResponse, status_code=201)
async def create_vendor(
    body: VendorCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    vendor = Vendor(
        name=body.name,
        external_id=body.external_id,
        category=body.category,
        daily_limit=body.daily_limit,
        monthly_limit=body.monthly_limit,
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.get("/", response_model=list[VendorResponse])
async def list_vendors(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    result = await db.execute(
        select(Vendor).order_by(Vendor.created_at.desc()).offset(offset).limit(limit)
    )
    return result.scalars().all()


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(vendor_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Vendor).where(Vendor.id == vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


@router.patch("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: uuid.UUID,
    body: VendorUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(select(Vendor).where(Vendor.id == vendor_id))
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    update_data = body.model_dump(exclude_unset=True)
    # Convert enum to string value if present
    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = update_data["status"].value

    for field, value in update_data.items():
        setattr(vendor, field, value)

    await db.commit()
    await db.refresh(vendor)
    return vendor
