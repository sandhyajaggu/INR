"""Staff Management. Only super_admin may create/delete other staff accounts."""

from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import CurrentUser, DbSession, require_super_admin
from app.core.security import hash_password
from app.models.staff import StaffUser
from app.schemas.common import PaginatedResponse
from app.schemas.staff import StaffCreate, StaffOut, StaffUpdate

router = APIRouter(prefix="/staff", tags=["Staff Management"], dependencies=[Depends(require_super_admin)])


@router.get("", response_model=PaginatedResponse[StaffOut], summary="List staff accounts (super_admin only)")
async def list_staff(
    db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)
) -> PaginatedResponse[StaffOut]:
    total = (await db.execute(select(func.count()).select_from(StaffUser))).scalar_one()
    stmt = select(StaffUser).order_by(StaffUser.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=ceil(total / page_size) if page_size else 0
    )


@router.get("/{staff_id}", response_model=StaffOut, summary="Get one staff account (super_admin only)")
async def get_staff(staff_id: int, db: DbSession) -> StaffUser:
    obj = await db.get(StaffUser, staff_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff user not found")
    return obj


@router.post(
    "",
    response_model=StaffOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a staff account (super_admin only)",
)
async def create_staff(payload: StaffCreate, db: DbSession) -> StaffUser:
    data = payload.model_dump()
    plain_password = data.pop("password")
    obj = StaffUser(**data, password_hash=hash_password(plain_password))
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists") from exc
    await db.refresh(obj)
    return obj


@router.put("/{staff_id}", response_model=StaffOut, summary="Update a staff account (super_admin only)")
async def update_staff(staff_id: int, payload: StaffUpdate, db: DbSession) -> StaffUser:
    obj = await db.get(StaffUser, staff_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff user not found")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        obj.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete(
    "/{staff_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a staff account (super_admin only)"
)
async def delete_staff(staff_id: int, current_user: CurrentUser, db: DbSession) -> None:
    if staff_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")
    obj = await db.get(StaffUser, staff_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff user not found")
    await db.delete(obj)
    await db.commit()
