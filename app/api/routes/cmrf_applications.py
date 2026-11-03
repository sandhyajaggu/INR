"""CMRF Applications page (frontend: CMRF.jsx, CMRFFormModal, CMRFDrawer, UploadCMRFModal, mockCmrfApi).

    GET    /cmrf-applications                     getAll()           array (q / mandal / status filters)
    GET    /cmrf-applications/summary             cards: total, approved, underReview, rejected, pending, approvedAmount
    GET    /cmrf-applications/{id}                one application
    POST   /cmrf-applications                     create(data)
    PUT    /cmrf-applications/{id}                update(id, data)   (also used to replace documents)
    PATCH  /cmrf-applications/{id}/status         updateStatus(id, status)
    POST   /cmrf-applications/{id}/documents      attach one document {type, name, url}
    DELETE /cmrf-applications/{id}                delete(id)         -> {"success": true}
    POST   /cmrf-applications/bulk-upload         Applicant Name, Mobile, Caste, Purpose, Hospital, Amount, Mandal, Village

Ids look like "CMRF-2026-12"; path params accept that, "CMRF-12" or "12".
"""

from datetime import timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, or_, select

from app.core.dependencies import DbSession, page_access
from app.core.ids import parse_id
from app.core.scope import resolve_scope
from app.models.cmrf import CMRF_STATUSES, CmrfApplication
from app.models.geography import Mandal, Village
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError, capped_error_detail
from app.schemas.common import coerce_excel_cell_to_str, validate_epic_no, validate_mobile_number
from app.services.activity_service import log_activity
from app.services.excel_import_service import parse_upload_rows
from app.services.geography_service import load_geography_maps, name_maps, resolve_geography

router = APIRouter(prefix="/cmrf-applications", tags=["CMRF Applications"])

CanView = page_access("cmrf_applications", "view")
CanEdit = page_access("cmrf_applications", "edit")
CanDelete = page_access("cmrf_applications", "admin")

IST = timezone(timedelta(hours=5, minutes=30))
DOCUMENT_TYPES = ("Hospital estimate", "Discharge summary", "Ration card", "Medical bills", "Other")


def _clean_text(v: object) -> object:
    v = coerce_excel_cell_to_str(v)
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _clean_amount(v: object) -> object:
    if isinstance(v, str):
        return v.replace(",", "").replace("₹", "").strip()
    return v


def _canonical_status(v: object) -> str:
    if v is None or str(v).strip() == "":
        return "Pending"
    for s in CMRF_STATUSES:
        if s.lower() == str(v).strip().lower():
            return s
    raise ValueError(f"status must be one of: {', '.join(CMRF_STATUSES)}")


class CmrfDocument(BaseModel):
    type: str = Field(default="Other", max_length=50)
    name: str = Field(min_length=1, max_length=255)
    url: str | None = None


class CmrfCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    applicant_name: str = Field(min_length=1, max_length=150)
    mobile: str
    caste: str | None = None
    purpose: str = Field(min_length=1, max_length=100)
    hospital: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)
    mandal: str
    village: str
    status: str = "Pending"
    epic_no: str | None = None
    remarks: str | None = None
    documents: list[CmrfDocument] | None = None

    @field_validator("applicant_name", "caste", "purpose", "hospital", "mandal", "village", "remarks", "epic_no", mode="before")
    @classmethod
    def _text(cls, v: object) -> object:
        return _clean_text(v)

    @field_validator("mobile", mode="before")
    @classmethod
    def _mobile(cls, v: object) -> str:
        value = validate_mobile_number(coerce_excel_cell_to_str(v))
        if value is None:
            raise ValueError("mobile is required")
        return value

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v: object) -> object:
        return _clean_amount(v)

    @field_validator("epic_no")
    @classmethod
    def _epic(cls, v: str | None) -> str | None:
        return validate_epic_no(v)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        return _canonical_status(v)


class CmrfUpdate(BaseModel):
    """Edit form (all fields) or a partial update such as {"documents": [...]}."""

    model_config = ConfigDict(extra="ignore")

    applicant_name: str | None = Field(default=None, min_length=1, max_length=150)
    mobile: str | None = None
    caste: str | None = None
    purpose: str | None = Field(default=None, min_length=1, max_length=100)
    hospital: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, gt=0)
    mandal: str | None = None
    village: str | None = None
    status: str | None = None
    epic_no: str | None = None
    remarks: str | None = None
    documents: list[CmrfDocument] | None = None

    @field_validator("applicant_name", "caste", "purpose", "hospital", "mandal", "village", "remarks", "epic_no", mode="before")
    @classmethod
    def _text(cls, v: object) -> object:
        return _clean_text(v)

    @field_validator("mobile", mode="before")
    @classmethod
    def _mobile(cls, v: object) -> str | None:
        return validate_mobile_number(coerce_excel_cell_to_str(v))

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v: object) -> object:
        return _clean_amount(v)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        return _canonical_status(v)

    @field_validator("epic_no")
    @classmethod
    def _epic(cls, v: str | None) -> str | None:
        return validate_epic_no(v)


class StatusUpdate(BaseModel):
    status: str

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        return _canonical_status(v)


CMRF_HEADER_ALIASES = {"name": "applicant_name", "applicant": "applicant_name", "mandal_name": "mandal", "village_name": "village"}


def display_id(app: CmrfApplication) -> str:
    year = (app.submitted_at or app.created_at).astimezone(IST).year if (app.submitted_at or app.created_at) else ""
    return f"CMRF-{year}-{app.id}"


async def cmrf_rows(db, apps: list[CmrfApplication]) -> list[dict[str, Any]]:
    mandals, villages = await name_maps(db, {a.mandal_id for a in apps}, {a.village_id for a in apps})
    out = []
    for a in apps:
        submitted = a.submitted_at.astimezone(IST) if a.submitted_at else None
        out.append(
            {
                "id": display_id(a),
                "applicant_name": a.applicant_name,
                "mobile": a.mobile,
                "caste": a.caste,
                "purpose": a.purpose,
                "hospital": a.hospital,
                "amount": float(a.amount),
                "mandal": mandals.get(a.mandal_id),
                "village": villages.get(a.village_id),
                "epic_no": a.epic_no,
                "status": a.status,
                "remarks": a.remarks,
                "documents": a.documents or [],
                "submitted_on": submitted.strftime("%d %b %Y") if submitted else None,
                "submittedAt": a.submitted_at,
                "createdAt": a.created_at,
                "updatedAt": a.updated_at,
            }
        )
    return out


async def _get(db, app_id: str) -> CmrfApplication:
    obj = await db.get(CmrfApplication, parse_id(app_id, label="Application"), populate_existing=True)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return obj


async def list_cmrf_rows(db, *, scope=None, q=None, mandal=None, status_filter=None, limit=None) -> list[dict[str, Any]]:
    stmt = select(CmrfApplication).join(Mandal, Mandal.id == CmrfApplication.mandal_id).join(
        Village, Village.id == CmrfApplication.village_id
    )
    if scope is not None:
        stmt = scope.apply(stmt, mandal_col=CmrfApplication.mandal_id)
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if status_filter:
        stmt = stmt.where(CmrfApplication.status == status_filter)
    if q and q.strip():
        term = f"%{q.strip()}%"
        conditions = [
            CmrfApplication.applicant_name.ilike(term),
            CmrfApplication.mobile.ilike(term),
            CmrfApplication.purpose.ilike(term),
            CmrfApplication.hospital.ilike(term),
            Mandal.name.ilike(term),
            Village.name.ilike(term),
        ]
        last_part = q.strip().split("-")[-1]
        if q.strip().upper().startswith("CMRF") and last_part.isdigit():
            conditions.append(CmrfApplication.id == int(last_part))
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(CmrfApplication.submitted_at.desc(), CmrfApplication.id.desc())
    if limit:
        stmt = stmt.limit(limit)
    return await cmrf_rows(db, list((await db.execute(stmt)).scalars().all()))


@router.get("", summary="List CMRF applications")
async def list_applications(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None),
    mandal: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
) -> list[dict[str, Any]]:
    return await list_cmrf_rows(db, scope=await resolve_scope(db, current_user), q=q, mandal=mandal, status_filter=status_filter)


@router.get("/summary", summary="CMRF page summary cards")
async def cmrf_summary(db: DbSession, current_user: CanView) -> dict[str, Any]:
    scope = await resolve_scope(db, current_user)
    stmt = select(
        func.count(),
        func.count().filter(CmrfApplication.status == "Approved"),
        func.count().filter(CmrfApplication.status == "Under Review"),
        func.count().filter(CmrfApplication.status == "Rejected"),
        func.count().filter(CmrfApplication.status == "Pending"),
        func.coalesce(func.sum(CmrfApplication.amount).filter(CmrfApplication.status == "Approved"), 0),
    ).select_from(CmrfApplication)
    total, approved, review, rejected, pending, amount = (
        await db.execute(scope.apply(stmt, mandal_col=CmrfApplication.mandal_id))
    ).one()
    return {
        "total": total,
        "approved": approved,
        "underReview": review,
        "rejected": rejected,
        "pending": pending,
        "approvedAmount": float(amount),
    }


@router.post("/bulk-upload", response_model=BulkImportResult, summary="Bulk-import CMRF applications")
async def bulk_upload(file: UploadFile, db: DbSession, current_user: CanEdit) -> BulkImportResult:
    rows = await parse_upload_rows(
        file,
        required_columns={"applicant_name", "mobile", "purpose", "hospital", "amount", "mandal", "village"},
        aliases=CMRF_HEADER_ALIASES,
    )
    errors: list[BulkImportRowError] = []
    mandal_map, village_map, _ = await load_geography_maps(db)
    ready = []
    for raw in rows:
        row_num = raw["_row_number"]
        try:
            p = CmrfCreate.model_validate(raw)
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
            errors.append(BulkImportRowError(row=row_num, reason=reason))
            continue
        mandal_id = mandal_map.get(p.mandal.lower())
        village_id = village_map.get((mandal_id, p.village.lower())) if mandal_id else None
        if mandal_id is None or village_id is None:
            errors.append(BulkImportRowError(row=row_num, reason=f"Unknown mandal/village '{p.mandal}' / '{p.village}'"))
            continue
        ready.append((p, mandal_id, village_id))
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(errors))
    for p, mandal_id, village_id in ready:
        db.add(
            CmrfApplication(
                applicant_name=p.applicant_name, mobile=p.mobile, caste=p.caste, purpose=p.purpose,
                hospital=p.hospital, amount=p.amount, mandal_id=mandal_id, village_id=village_id,
                status=p.status, epic_no=p.epic_no, created_by=current_user.id,
            )
        )
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="cmrf_bulk_imported", module="CMRF",
        reference_id=None, description=f"Bulk import: {len(ready)} CMRF applications added",
    )
    await db.commit()
    return BulkImportResult(inserted=len(ready), errors=[])


@router.get("/{app_id}", summary="Get one CMRF application")
async def get_application(app_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    return (await cmrf_rows(db, [await _get(db, app_id)]))[0]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a CMRF application")
async def create_application(payload: CmrfCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    mandal_id, village_id = await resolve_geography(db, mandal_name=payload.mandal, village_name=payload.village)
    data = payload.model_dump(exclude={"mandal", "village", "documents"})
    obj = CmrfApplication(
        **data,
        mandal_id=mandal_id,
        village_id=village_id,
        documents=[d.model_dump() for d in payload.documents or []],
        created_by=current_user.id,
    )
    db.add(obj)
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="cmrf_added", module="CMRF", reference_id=obj.id,
        description=f"Added CMRF application for {obj.applicant_name} (₹{obj.amount:,.0f})",
    )
    await db.commit()
    return (await cmrf_rows(db, [await _get(db, str(obj.id))]))[0]


async def _apply_update(db, obj: CmrfApplication, data: dict[str, Any]) -> None:
    if "mandal" in data or "village" in data:
        mandal_name = data.pop("mandal", None)
        village_name = data.pop("village", None)
        if mandal_name:
            obj.mandal_id, obj.village_id = await resolve_geography(db, mandal_name=mandal_name, village_name=village_name)
    if "documents" in data:
        data["documents"] = [d if isinstance(d, dict) else d.model_dump() for d in (data["documents"] or [])]
    for field, value in data.items():
        setattr(obj, field, value)


@router.put("/{app_id}", summary="Update a CMRF application (any subset of fields)")
async def update_application(app_id: str, payload: CmrfUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, app_id)
    before = (await cmrf_rows(db, [obj]))[0]
    await _apply_update(db, obj, payload.model_dump(exclude_unset=True))
    await db.commit()
    after = (await cmrf_rows(db, [await _get(db, app_id)]))[0]
    keys = ("applicant_name", "mobile", "caste", "purpose", "hospital", "amount", "mandal", "village", "status")
    changes = [[k, str(before[k] or "—"), str(after[k] or "—")] for k in keys if before[k] != after[k]]
    if len(before["documents"]) != len(after["documents"]):
        changes.append(["documents", str(len(before["documents"])), str(len(after["documents"]))])
    await log_activity(
        db, actor_id=current_user.id, action_type="cmrf_updated", module="CMRF", reference_id=obj.id,
        description=f"Updated CMRF application {after['id']}", changes=changes, commit=True,
    )
    return after


@router.patch("/{app_id}/status", summary="Change an application's status")
async def update_status(app_id: str, payload: StatusUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, app_id)
    old = obj.status
    obj.status = payload.status
    await log_activity(
        db, actor_id=current_user.id, action_type="cmrf_status_changed", module="CMRF", reference_id=obj.id,
        description=f"CMRF application {display_id(obj)}: {old} → {payload.status}",
        changes=[["status", old, payload.status]],
    )
    await db.commit()
    return (await cmrf_rows(db, [await _get(db, app_id)]))[0]


@router.post("/{app_id}/documents", summary="Attach a document")
async def attach_document(app_id: str, payload: CmrfDocument, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, app_id)
    obj.documents = [*(obj.documents or []), payload.model_dump()]
    await log_activity(
        db, actor_id=current_user.id, action_type="cmrf_document_added", module="CMRF", reference_id=obj.id,
        description=f"Attached {payload.type} '{payload.name}' to {display_id(obj)}",
    )
    await db.commit()
    return (await cmrf_rows(db, [await _get(db, app_id)]))[0]


@router.delete("/{app_id}", summary="Delete a CMRF application")
async def delete_application(app_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, app_id)
    await log_activity(
        db, actor_id=current_user.id, action_type="cmrf_deleted", module="CMRF", reference_id=obj.id,
        description=f"Deleted CMRF application {display_id(obj)} ({obj.applicant_name})",
    )
    await db.delete(obj)
    await db.commit()
    return {"success": True}
