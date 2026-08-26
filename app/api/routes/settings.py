"""app_settings is a single-row table (Constituency Information tab)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession, require_staff
from app.models.settings import AppSettings
from app.schemas.settings import AppSettingsOut, AppSettingsUpdate

router = APIRouter(prefix="/settings", tags=["Settings"])


async def _get_or_create_settings_row(db: DbSession) -> AppSettings:
    obj = (await db.execute(select(AppSettings).limit(1))).scalar_one_or_none()
    if obj is None:
        obj = AppSettings()
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
    return obj


@router.get("", response_model=AppSettingsOut, summary="Get constituency/app settings")
async def get_settings(db: DbSession, current_user: CurrentUser) -> AppSettings:
    return await _get_or_create_settings_row(db)


@router.put(
    "",
    response_model=AppSettingsOut,
    summary="Update constituency/app settings",
    dependencies=[Depends(require_staff)],
)
async def update_settings(payload: AppSettingsUpdate, db: DbSession) -> AppSettings:
    obj = await _get_or_create_settings_row(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj
