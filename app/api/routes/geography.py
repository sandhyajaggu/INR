"""Mandal / village name lists for dropdowns (e.g. Booth Summary "Select Mandal")."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.dependencies import CurrentUser, DbSession
from app.models.geography import Mandal, Village
from app.schemas.geography import MandalNameOut, VillageNameOut

router = APIRouter(tags=["Geography"])


@router.get("/mandals", response_model=list[MandalNameOut], summary="List mandal names")
async def list_mandals(db: DbSession, current_user: CurrentUser) -> list[MandalNameOut]:
    names = (await db.execute(select(Mandal.name).order_by(Mandal.name))).scalars().all()
    return [MandalNameOut(name=n) for n in names]


@router.get("/villages", response_model=list[VillageNameOut], summary="List village names in a mandal")
async def list_villages(
    db: DbSession,
    current_user: CurrentUser,
    mandal_name: str = Query(..., description="Mandal name, e.g. Kandukur"),
) -> list[VillageNameOut]:
    mandal_id = (
        await db.execute(select(Mandal.id).where(func.lower(Mandal.name) == mandal_name.strip().lower()))
    ).scalar_one_or_none()
    if mandal_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown mandal '{mandal_name}'")
    names = (
        await db.execute(select(Village.name).where(Village.mandal_id == mandal_id).order_by(Village.name))
    ).scalars().all()
    return [VillageNameOut(name=n) for n in names]
