from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.core.crud_router import build_crud_router
from app.core.dependencies import CurrentUser, DbSession, RequireStaff
from app.models.development_works import DevelopmentWork
from app.schemas.bulk_import import BulkImportResult
from app.schemas.development_works import (
    DevelopmentStatusSummary,
    DevelopmentWorkCreate,
    DevelopmentWorkOut,
    DevelopmentWorkUpdate,
)
from app.services.development_work_service import bulk_import_development_works
from app.services.excel_import_service import parse_excel_rows

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


@extra_router.post(
    "/bulk-upload",
    response_model=BulkImportResult,
    summary="Bulk-import development works from an Excel (.xlsx) sheet",
    description=(
        "All-or-nothing import: every row is validated first (required fields, "
        "mandal_name/village_name resolvable). If any row fails, nothing is "
        "written and the full list of row errors is returned instead."
    ),
)
async def bulk_upload_development_works(
    file: UploadFile, db: DbSession, current_user: RequireStaff
) -> BulkImportResult:
    rows = await parse_excel_rows(file, required_columns={"title", "mandal_name"})
    result = await bulk_import_development_works(db, rows, actor_id=current_user.id)
    if result.errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=[e.model_dump() for e in result.errors]
        )
    return result


# NOTE: main.py must include extra_router BEFORE router — otherwise the
# generic "/{item_id}" route (a bare, un-typed path param) would swallow
# "/development-works/status-summary" and 422 on it instead of matching this.
