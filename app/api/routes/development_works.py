from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.crud_router import build_crud_router
from app.core.dependencies import CurrentUser, DbSession
from app.models.development_works import DevelopmentWork
from app.schemas.development_works import (
    DevelopmentStatusSummary,
    DevelopmentWorkCreate,
    DevelopmentWorkOut,
    DevelopmentWorkUpdate,
)

router = build_crud_router(
    model=DevelopmentWork,
    create_schema=DevelopmentWorkCreate,
    update_schema=DevelopmentWorkUpdate,
    out_schema=DevelopmentWorkOut,
    prefix="/development-works",
    tags=["Development Works"],
    resource_label="development works",
    search_field="title",
    activity_module="development_works",
    name_field="title",
)

extra_router = APIRouter(prefix="/development-works", tags=["Development Works"])


@extra_router.get(
    "/status-summary",
    response_model=list[DevelopmentStatusSummary],
    summary="Development works count by status (v_development_status_summary)",
)
async def status_summary(db: DbSession, current_user: CurrentUser) -> list[DevelopmentStatusSummary]:
    stmt = select(DevelopmentWork.status, func.count().label("total")).group_by(DevelopmentWork.status)
    rows = (await db.execute(stmt)).all()
    return [DevelopmentStatusSummary(status=row.status, total=row.total) for row in rows]


# NOTE: main.py must include extra_router BEFORE router — otherwise the
# generic "/{item_id}" route (a bare, un-typed path param) would swallow
# "/development-works/status-summary" and 422 on it instead of matching this.
