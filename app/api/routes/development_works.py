"""Development Works page (frontend: Development.js, mockDevelopmentApi).

    GET    /development-works                   listWorks()   (array; q / mandal / status / category filters)
    GET    /development-works/status-summary    count by status
    GET    /development-works/{id}              one work
    POST   /development-works                   createWork(data)
    PUT    /development-works/{id}              updateWork(id, data)
    DELETE /development-works/{id}              deleteWork(id)  -> {"success": true}
    POST   /development-works/bulk-upload       .xlsx / .xls / .csv (frontend template headers)
    GET    /development-works/bulk-upload/template

Ids are "DW-<n>"; path params accept "DW-12" or "12". Records:
    id, name, category, mandal, village, budget, fund_source, start_date,
    completion_date, progress, status, contractor, contractor_te, remarks,
    photo, completed_photo, days_since_update, createdAt, updatedAt
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.core.scope import resolve_scope
from app.models.development_works import DevelopmentWork
from app.models.geography import Mandal, Village
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError, capped_error_detail
from app.schemas.development_works import (
    DEV_HEADER_ALIASES,
    DevelopmentStatusSummary,
    DevelopmentWorkBulkRow,
    DevelopmentWorkCreate,
    DevelopmentWorkUpdate,
)
from app.services.activity_service import log_activity
from app.services.bulk_template_service import (
    XLSX_MEDIA_TYPE,
    TemplateColumn,
    TemplateSheet,
    build_single_sheet_template,
    mandal_names,
    standard_notes,
    xlsx_attachment_headers,
)
from app.services.excel_import_service import parse_upload_rows
from app.services.geography_service import load_geography_maps, name_maps, resolve_geography

router = APIRouter(prefix="/development-works", tags=["Development Works"])

CanView = page_access("development_works", "view")
CanEdit = page_access("development_works", "edit")
CanDelete = page_access("development_works", "admin")

PREFIX = "DW"


async def work_rows(db, works: list[DevelopmentWork]) -> list[dict[str, Any]]:
    mandals, villages = await name_maps(db, {w.mandal_id for w in works}, {w.village_id for w in works})
    now = datetime.now(timezone.utc)
    return [
        {
            "id": format_id(PREFIX, w.id),
            "name": w.title,
            "category": w.category,
            "mandal": mandals.get(w.mandal_id),
            "village": villages.get(w.village_id),
            "budget": float(w.estimated_cost) if w.estimated_cost is not None else 0,
            "fund_source": w.fund_source,
            "start_date": w.start_date.isoformat() if w.start_date else None,
            "completion_date": w.completion_date.isoformat() if w.completion_date else None,
            "progress": w.progress,
            "status": w.status,
            "contractor": w.contractor,
            "contractor_te": w.contractor_te,
            "remarks": w.description,
            "photo": w.photo_url,
            "completed_photo": w.completed_photo_url,
            "days_since_update": (now - w.updated_at).days if w.updated_at else 0,
            "createdAt": w.created_at,
            "updatedAt": w.updated_at,
        }
        for w in works
    ]


async def _values(db, payload: DevelopmentWorkCreate) -> dict[str, Any]:
    mandal_id, village_id = await resolve_geography(db, mandal_name=payload.mandal, village_name=payload.village)
    return {
        "title": payload.name,
        "category": payload.category,
        "fund_source": payload.fund_source,
        "mandal_id": mandal_id,
        "village_id": village_id,
        "estimated_cost": payload.budget,
        "contractor": payload.contractor,
        "contractor_te": payload.contractor_te,
        "start_date": payload.start_date,
        "work_date": payload.start_date,
        "completion_date": payload.completion_date,
        "progress": payload.progress,
        "status": payload.status,
        "description": payload.remarks,
        "photo_url": payload.photo,
        "completed_photo_url": payload.completed_photo,
    }


async def list_work_rows(db, *, scope=None, q=None, mandal=None, status_filter=None, category=None) -> list[dict[str, Any]]:
    stmt = select(DevelopmentWork).outerjoin(Mandal, Mandal.id == DevelopmentWork.mandal_id).outerjoin(
        Village, Village.id == DevelopmentWork.village_id
    )
    if scope is not None:
        stmt = scope.apply(stmt, mandal_col=DevelopmentWork.mandal_id)
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if status_filter:
        stmt = stmt.where(DevelopmentWork.status == status_filter)
    if category:
        stmt = stmt.where(DevelopmentWork.category == category)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                DevelopmentWork.title.ilike(term),
                DevelopmentWork.category.ilike(term),
                DevelopmentWork.contractor.ilike(term),
                Mandal.name.ilike(term),
                Village.name.ilike(term),
            )
        )
    works = list((await db.execute(stmt.order_by(DevelopmentWork.id.desc()))).scalars().all())
    return await work_rows(db, works)


async def _get(db, work_id: str) -> DevelopmentWork:
    work = await db.get(DevelopmentWork, parse_id(work_id, label="Work"), populate_existing=True)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work not found")
    return work


@router.get("", summary="List development works")
async def list_works(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None),
    mandal: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = Query(None),
) -> list[dict[str, Any]]:
    return await list_work_rows(
        db, scope=await resolve_scope(db, current_user), q=q, mandal=mandal, status_filter=status_filter, category=category
    )


@router.get("/status-summary", response_model=list[DevelopmentStatusSummary], summary="Works count by status")
async def status_summary(db: DbSession, current_user: CanView) -> list[DevelopmentStatusSummary]:
    stmt = select(DevelopmentWork.status, func.count().label("total")).group_by(DevelopmentWork.status)
    return [DevelopmentStatusSummary(status=r.status, total=r.total) for r in (await db.execute(stmt)).all()]


def _template_columns(mandals: list[str]) -> list[TemplateColumn]:
    return [
        TemplateColumn("Work ID", False, "Leave blank: ids are assigned automatically"),
        TemplateColumn("Work Name", True, "Name of the work"),
        TemplateColumn("Category", False, "e.g. Drinking Water, Roads & Bridges"),
        TemplateColumn("Mandal", True, "One of the mandals in the dropdown", choices=mandals or None),
        TemplateColumn("Village", False, "Village in that mandal"),
        TemplateColumn("Sanctioned Budget (₹)", True, "Amount in rupees"),
        TemplateColumn("Fund Source", False, "State Government, Central Government, MLA Development Fund, ..."),
        TemplateColumn("Start Date", False, "YYYY-MM-DD", as_text=True),
        TemplateColumn("Completion Date", False, "YYYY-MM-DD (required when Status is Completed)", as_text=True),
        TemplateColumn("Progress %", False, "0-100"),
        TemplateColumn("Status", False, "Not Started, In Progress or Completed",
                       choices=["Not Started", "In Progress", "Completed"]),
        TemplateColumn("Contractor", False, "Contractor name"),
        TemplateColumn("Remarks", False, "Notes"),
    ]


@router.get(
    "/bulk-upload/template",
    summary="Download the development works upload template (.xlsx)",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
async def download_template(db: DbSession, current_user: CanEdit) -> Response:
    example = [["", "Drinking Water Overhead Tank", "Drinking Water", "Kandukur", "Kandukur Town", 500000,
                "State Government", "2026-03-10", "", 40, "In Progress", "Rao Infra Projects", ""]]
    spec = TemplateSheet("Development Works", _template_columns(await mandal_names(db)), example)
    return Response(
        content=build_single_sheet_template(spec, standard_notes()),
        media_type=XLSX_MEDIA_TYPE,
        headers=xlsx_attachment_headers("development_works_template.xlsx"),
    )


@router.post("/bulk-upload", response_model=BulkImportResult, summary="Bulk-import development works")
async def bulk_upload(file: UploadFile, db: DbSession, current_user: CanEdit) -> BulkImportResult:
    rows = await parse_upload_rows(file, required_columns={"name", "mandal", "budget"}, aliases=DEV_HEADER_ALIASES)
    errors: list[BulkImportRowError] = []
    parsed: list[tuple[int, DevelopmentWorkBulkRow]] = []
    for raw in rows:
        try:
            parsed.append((raw["_row_number"], DevelopmentWorkBulkRow.model_validate(raw)))
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'row'}: {e['msg']}" for e in exc.errors())
            errors.append(BulkImportRowError(row=raw["_row_number"], reason=reason))
    mandal_map, village_map, _ = await load_geography_maps(db)
    values = []
    for row_num, p in parsed:
        mandal_id = mandal_map.get(p.mandal.lower())
        if mandal_id is None:
            errors.append(BulkImportRowError(row=row_num, reason=f"Unknown mandal '{p.mandal}'"))
            continue
        village_id = None
        if p.village:
            village_id = village_map.get((mandal_id, p.village.lower()))
            if village_id is None:
                errors.append(BulkImportRowError(row=row_num, reason=f"Unknown village '{p.village}' in mandal '{p.mandal}'"))
                continue
        values.append((p, mandal_id, village_id))
    if errors:
        errors.sort(key=lambda e: e.row)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(errors))
    for p, mandal_id, village_id in values:
        db.add(
            DevelopmentWork(
                title=p.name, category=p.category, fund_source=p.fund_source, mandal_id=mandal_id,
                village_id=village_id, estimated_cost=p.budget, contractor=p.contractor, start_date=p.start_date,
                work_date=p.start_date, completion_date=p.completion_date, progress=p.progress, status=p.status,
                description=p.remarks, created_by=current_user.id,
            )
        )
    await db.flush()
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="development_works_bulk_imported",
        module="development_works",
        reference_id=None,
        description=f"Bulk import: {len(values)} development works added",
    )
    await db.commit()
    return BulkImportResult(inserted=len(values), errors=[])


@router.get("/{work_id}", summary="Get one development work")
async def get_work(work_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    return (await work_rows(db, [await _get(db, work_id)]))[0]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a development work")
async def create_work(payload: DevelopmentWorkCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    work = DevelopmentWork(**await _values(db, payload), created_by=current_user.id)
    db.add(work)
    await db.flush()
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="development_works_added",
        module="development_works",
        reference_id=work.id,
        description=f"Added development work {format_id(PREFIX, work.id)} ({work.title})",
    )
    await db.commit()
    return (await work_rows(db, [await _get(db, str(work.id))]))[0]


@router.put("/{work_id}", summary="Update a development work")
async def update_work(work_id: str, payload: DevelopmentWorkUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    work = await _get(db, work_id)
    before = (await work_rows(db, [work]))[0]
    for field, value in (await _values(db, payload)).items():
        setattr(work, field, value)
    await db.commit()
    after = (await work_rows(db, [await _get(db, work_id)]))[0]
    keys = ("name", "category", "mandal", "village", "budget", "fund_source", "start_date", "completion_date",
            "progress", "status", "contractor", "remarks")
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="development_works_updated",
        module="development_works",
        reference_id=work.id,
        description=f"Updated development work {after['id']} ({after['name']})",
        changes=[[k, str(before[k] if before[k] is not None else "—"), str(after[k] if after[k] is not None else "—")]
                 for k in keys if before[k] != after[k]],
        commit=True,
    )
    return after


@router.delete("/{work_id}", summary="Delete a development work")
async def delete_work(work_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    work = await _get(db, work_id)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="development_works_deleted",
        module="development_works",
        reference_id=work.id,
        description=f"Deleted development work {format_id(PREFIX, work.id)} ({work.title})",
    )
    await db.delete(work)
    await db.commit()
    return {"success": True}
