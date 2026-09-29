from fastapi import APIRouter, HTTPException, Response, UploadFile, status

from app.core.dependencies import CurrentUser, DbSession, RequireStaff
from app.schemas.bulk_import import BulkImportResult, capped_error_detail
from app.services.booth_import_service import build_booth_template, bulk_import_booths, parse_booth_upload

router = APIRouter(prefix="/booths", tags=["Booths"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/bulk-upload/template",
    summary="Download the booths bulk-upload sample template (.xlsx)",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
async def download_booth_template(current_user: CurrentUser) -> Response:
    return Response(
        content=build_booth_template(),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="booths_template.xlsx"'},
    )


@router.post(
    "/bulk-upload",
    response_model=BulkImportResult,
    summary="Bulk-import booths from an Excel (.xlsx / .xls) or CSV file",
    description=(
        "Columns: Booth No, In Charge, Mandal, Village, Registered Votes, TDP, YSP, Janasena, "
        "Status (On Time / Delayed) — all mandatory. A row whose Mandal + Booth No already exists "
        "updates that booth; other rows add new booths. All-or-nothing: if any row fails, nothing "
        "is written and the full list of row errors is returned instead."
    ),
)
async def bulk_upload_booths(file: UploadFile, db: DbSession, current_user: RequireStaff) -> BulkImportResult:
    rows = await parse_booth_upload(file)
    result = await bulk_import_booths(db, rows, actor_id=current_user.id)
    if result.errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(result.errors))
    return result
