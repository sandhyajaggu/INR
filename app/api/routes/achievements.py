"""Bespoke because the list is public (no auth) while writes are staff-only."""

from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentUser, DbSession, require_staff, require_super_admin
from app.models.achievements import Achievement
from app.schemas.achievements import AchievementCreate, AchievementOut, AchievementUpdate
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/achievements", tags=["Achievements"])


@router.get("", response_model=PaginatedResponse[AchievementOut], summary="List achievements (public)")
async def list_achievements(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    category: str | None = Query(None),
    q: str | None = Query(None, description="Search title"),
) -> PaginatedResponse[AchievementOut]:
    stmt = select(Achievement).where(Achievement.status == "active")
    count_stmt = select(func.count()).select_from(Achievement).where(Achievement.status == "active")
    if category:
        stmt = stmt.where(Achievement.category == category)
        count_stmt = count_stmt.where(Achievement.category == category)
    if q:
        stmt = stmt.where(Achievement.title.ilike(f"%{q}%"))
        count_stmt = count_stmt.where(Achievement.title.ilike(f"%{q}%"))

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Achievement.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=ceil(total / page_size) if page_size else 0
    )


@router.get("/{achievement_id}", response_model=AchievementOut, summary="Get one achievement (public)")
async def get_achievement(achievement_id: int, db: DbSession) -> Achievement:
    obj = await db.get(Achievement, achievement_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Achievement not found")
    return obj


@router.post(
    "",
    response_model=AchievementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an achievement (staff-only)",
    dependencies=[Depends(require_staff)],
)
async def create_achievement(payload: AchievementCreate, db: DbSession) -> Achievement:
    obj = Achievement(**payload.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put(
    "/{achievement_id}",
    response_model=AchievementOut,
    summary="Update an achievement (staff-only)",
    dependencies=[Depends(require_staff)],
)
async def update_achievement(achievement_id: int, payload: AchievementUpdate, db: DbSession) -> Achievement:
    obj = await db.get(Achievement, achievement_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Achievement not found")
    for field, value in payload.model_dump().items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete(
    "/{achievement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an achievement (super_admin only)",
    dependencies=[Depends(require_super_admin)],
)
async def delete_achievement(achievement_id: int, db: DbSession) -> None:
    obj = await db.get(Achievement, achievement_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Achievement not found")
    await db.delete(obj)
    await db.commit()
