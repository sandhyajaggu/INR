"""Beneficiaries page (frontend: Beneficiaries.jsx, BeneficiaryFormModal, BeneficiaryDrawer,
UploadBeneficiariesModal, mockBeneficiariesApi) plus the older cross-scheme endpoints.

    GET    /beneficiaries                        getAll()  (paginated; scheme / q / status / mandal filters)
    GET    /beneficiaries/stats                  counts per scheme (the scheme tabs) + totals
    GET    /beneficiaries/voter-lookup/{epic}    lookupVoter(epic) -> {name, mandal, village, ...}
    POST   /beneficiaries                        create(data)
    PUT    /beneficiaries/{id}                   update(id, data)
    DELETE /beneficiaries/{id}                   delete(id) -> {"success": true}
    POST   /beneficiaries/bulk-upload            CSV / single sheet (Voter ID, Name, Scheme, Mandal, Village,
                                                 Amount, Status) or the older one-tab-per-scheme workbook
    GET    /beneficiaries/lookup/{epic}          every scheme an EPIC appears in
    GET    /beneficiaries/by-geography
    GET    /beneficiaries/{id}
    GET    /beneficiaries/{id}/aadhaar/reveal

Record shape: id ("BEN-<n>"), voter_id (EPIC), name, scheme (scheme name),
mandal, village, amount, status ("Pending" / "Approved" / "Disbursed" /
"Rejected"), the scheme's extra fields (student_name, student_class, school,
qualification, gas_connection_no, ...), createdAt, updatedAt.
The per-scheme routers (/beneficiaries/<scheme>) are unchanged.
"""

from decimal import Decimal
from math import ceil
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, or_, select, text

from app.core.dependencies import DbSession, RequireSuperAdmin, page_access
from app.core.ids import format_id, parse_id
from app.core.scope import resolve_scope
from app.models.geography import Mandal, Village
from app.models.schemes import Beneficiary, Scheme
from app.models.voters import Voter
from app.schemas.beneficiaries import BeneficiaryGeographyRow, BeneficiaryLookupResult
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError, capped_error_detail
from app.schemas.common import coerce_excel_cell_to_str, validate_epic_no
from app.services.activity_service import log_activity
from app.services.beneficiary_service import (
    SCHEME_REGISTRY,
    bulk_import_all_beneficiaries,
    bulk_row_schema,
    get_beneficiary_or_404,
)
from app.services.bulk_template_service import (
    XLSX_MEDIA_TYPE,
    TemplateSheet,
    build_multi_sheet_template,
    columns_from_schema,
    mandal_names,
    xlsx_attachment_headers,
)
from app.services.encryption_service import decrypt_aadhaar
from app.services.excel_import_service import parse_excel_workbook, parse_upload_rows
from app.services.geography_service import load_geography_maps, name_maps, resolve_geography

router = APIRouter(prefix="/beneficiaries", tags=["Beneficiaries"])

CanView = page_access("beneficiaries", "view")
CanEdit = page_access("beneficiaries", "edit")
CanDelete = page_access("beneficiaries", "admin")

PREFIX = "BEN"
CMRF_CODE = "cmrf"
STATUS_TO_UI = {"pending": "Pending", "approved": "Approved", "disbursed": "Disbursed", "rejected": "Rejected"}
CORE_FIELDS = {
    "id", "voter_id", "epic_no", "name", "scheme", "mandal", "village", "amount", "status", "remarks",
    "createdAt", "updatedAt", "created_at", "updated_at", "mobile", "photo", "document",
}


class BeneficiaryForm(BaseModel):
    """Add/Edit Beneficiary form. Unknown keys (student_name, school, qualification,
    gas_connection_no, ...) are kept as the scheme's extra details."""

    model_config = ConfigDict(extra="allow")

    voter_id: str
    name: str = Field(min_length=1, max_length=150)
    scheme: str = Field(min_length=1)
    mandal: str
    village: str
    amount: Decimal | None = Field(default=None, ge=0)
    status: str = "Pending"
    mobile: str | None = None
    remarks: str | None = None

    @field_validator("voter_id", mode="before")
    @classmethod
    def _epic(cls, v: object) -> str:
        epic = validate_epic_no(v)
        if epic is None:
            raise ValueError("voter_id (EPIC number) is required")
        return epic

    @field_validator("name", "scheme", "mandal", "village", "mobile", "remarks", mode="before")
    @classmethod
    def _text(cls, v: object) -> object:
        v = coerce_excel_cell_to_str(v)
        return v.strip() if isinstance(v, str) else v

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.replace(",", "").replace("₹", "").strip()
            return v or None
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        text_value = str(v or "Pending").strip().lower()
        if text_value not in STATUS_TO_UI:
            raise ValueError("status must be Pending, Approved, Disbursed or Rejected")
        return text_value

    def extras(self) -> dict[str, Any]:
        out = {}
        for key, value in (self.model_extra or {}).items():
            if key in CORE_FIELDS or isinstance(value, (dict, list)):
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            out[key] = value.strip() if isinstance(value, str) else value
        return out


BENEFICIARY_HEADER_ALIASES = {"voter_id": "voter_id", "epic_no": "voter_id", "epic": "voter_id", "scheme_name": "scheme",
                              "mandal_name": "mandal", "village_name": "village", "beneficiary_name": "name"}


async def find_scheme(db, label: str) -> Scheme:
    key = label.strip().lower()
    schemes = (await db.execute(select(Scheme))).scalars().all()
    for s in schemes:
        names = {s.scheme_name.lower(), s.scheme_code.lower(), (s.short_code or "").lower()}
        names |= {x.strip().lower() for x in (s.other_spellings or "").split(",") if x.strip()}
        if key in names:
            return s
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown scheme '{label}'")


async def beneficiary_rows(db, items: list[Beneficiary]) -> list[dict[str, Any]]:
    mandals, villages = await name_maps(db, {b.mandal_id for b in items}, {b.village_id for b in items})
    scheme_ids = {b.scheme_id for b in items}
    schemes = {}
    if scheme_ids:
        schemes = {s.id: s for s in (await db.execute(select(Scheme).where(Scheme.id.in_(scheme_ids)))).scalars().all()}
    out = []
    for b in items:
        s = schemes.get(b.scheme_id)
        row = {
            "id": format_id(PREFIX, b.id),
            "voter_id": b.epic_no,
            "name": b.beneficiary_name,
            "scheme": s.scheme_name if s else None,
            "scheme_code": s.scheme_code if s else None,
            "mandal": mandals.get(b.mandal_id),
            "village": villages.get(b.village_id),
            "amount": float(b.amount) if b.amount is not None else 0,
            "status": STATUS_TO_UI.get(b.status, b.status),
            "mobile": b.mobile_number,
            "remarks": b.remarks,
            "photo": b.photo_url,
            "document": b.document_url,
            "createdAt": b.created_at,
            "updatedAt": b.updated_at,
        }
        for key, value in (b.scheme_details or {}).items():
            row.setdefault(key, value)
        out.append(row)
    return out


async def _values(db, form: BeneficiaryForm) -> dict[str, Any]:
    scheme = await find_scheme(db, form.scheme)
    mandal_id, village_id = await resolve_geography(db, mandal_name=form.mandal, village_name=form.village)
    voter = (await db.execute(select(Voter).where(Voter.epic_no == form.voter_id))).scalar_one_or_none()
    amount = form.amount
    if amount is None and scheme.amount_per_beneficiary is not None:
        amount = scheme.amount_per_beneficiary
    return {
        "scheme_id": scheme.id,
        "voter_id": voter.id if voter else None,
        "epic_no": form.voter_id,
        "beneficiary_name": form.name,
        "mandal_id": mandal_id,
        "village_id": village_id,
        "amount": amount,
        "status": form.status,
        "mobile_number": form.mobile or (voter.mobile if voter else None),
        "remarks": form.remarks,
        "scheme_details": form.extras(),
    }


@router.get("", summary="List beneficiaries (paginated)")
async def list_beneficiaries(
    db: DbSession,
    current_user: CanView,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    scheme: str | None = Query(None, description='Scheme name (e.g. "Thalliki Vandanam") or code; "All schemes" = all'),
    q: str | None = Query(None, description="Search name, EPIC, mandal, village"),
    status_filter: str | None = Query(None, alias="status"),
    mandal: str | None = Query(None),
    include_cmrf: bool = Query(False),
) -> dict[str, Any]:
    stmt = (
        select(Beneficiary.id)
        .join(Scheme, Scheme.id == Beneficiary.scheme_id)
        .outerjoin(Mandal, Mandal.id == Beneficiary.mandal_id)
        .outerjoin(Village, Village.id == Beneficiary.village_id)
    )
    stmt = (await resolve_scope(db, current_user)).apply(stmt, mandal_col=Beneficiary.mandal_id)
    if not include_cmrf:
        stmt = stmt.where(Scheme.scheme_code != CMRF_CODE)
    if scheme and scheme.strip().lower() not in ("all", "all schemes"):
        stmt = stmt.where(Beneficiary.scheme_id == (await find_scheme(db, scheme)).id)
    if status_filter:
        stmt = stmt.where(Beneficiary.status == status_filter.strip().lower())
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Beneficiary.beneficiary_name.ilike(term),
                Beneficiary.epic_no.ilike(term),
                Mandal.name.ilike(term),
                Village.name.ilike(term),
            )
        )
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    ids = list((await db.execute(stmt.order_by(Beneficiary.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all())
    items = (await db.execute(select(Beneficiary).where(Beneficiary.id.in_(ids or [-1])))).scalars().all()
    by_id = {b.id: b for b in items}
    return {
        "items": await beneficiary_rows(db, [by_id[i] for i in ids if i in by_id]),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if page_size else 0,
    }


@router.get("/stats", summary="Beneficiaries per scheme (scheme tabs) and totals")
async def beneficiary_stats(db: DbSession, current_user: CanView, include_cmrf: bool = Query(False)) -> dict[str, Any]:
    stmt = (
        select(
            Scheme.scheme_name,
            func.count(Beneficiary.id),
            func.coalesce(func.sum(Beneficiary.amount).filter(Beneficiary.status == "disbursed"), 0),
        )
        .outerjoin(Beneficiary, Beneficiary.scheme_id == Scheme.id)
        .group_by(Scheme.id, Scheme.scheme_name)
        .order_by(Scheme.id)
    )
    if not include_cmrf:
        stmt = stmt.where(Scheme.scheme_code != CMRF_CODE)
    rows = (await db.execute(stmt)).all()
    total = sum(r[1] for r in rows)
    return {
        "total": total,
        "amountDisbursed": float(sum(r[2] for r in rows)),
        "schemes": [{"key": "All schemes", "count": total}] + [{"key": name, "count": n} for name, n, _ in rows],
    }


@router.get("/voter-lookup/{epic_no}", summary="Look up a voter by EPIC for the beneficiary form")
async def voter_lookup(epic_no: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    stmt = (
        select(Voter, Mandal.name, Village.name)
        .join(Mandal, Mandal.id == Voter.mandal_id)
        .join(Village, Village.id == Voter.village_id)
        .where(Voter.epic_no == epic_no.strip().upper(), Voter.removed_at.is_(None))
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voter not found")
    voter, mandal, village = row
    return {"epic_no": voter.epic_no, "name": voter.name, "mandal": mandal, "village": village, "mobile": voter.mobile}


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a beneficiary")
async def create_beneficiary(payload: BeneficiaryForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = Beneficiary(**await _values(db, payload), created_by=current_user.id)
    db.add(obj)
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="beneficiary_added", module="beneficiaries", reference_id=obj.id,
        description=f"Added beneficiary {obj.beneficiary_name} ({obj.epic_no}) to {payload.scheme}",
    )
    await db.commit()
    return (await beneficiary_rows(db, [await get_beneficiary_or_404(db, obj.id)]))[0]


@router.put("/{beneficiary_id}", summary="Update a beneficiary")
async def update_beneficiary(
    beneficiary_id: str, payload: BeneficiaryForm, db: DbSession, current_user: CanEdit
) -> dict[str, Any]:
    obj = await get_beneficiary_or_404(db, parse_id(beneficiary_id, label="Beneficiary"))
    before = (await beneficiary_rows(db, [obj]))[0]
    values = await _values(db, payload)
    values["scheme_details"] = {**(obj.scheme_details or {}), **values["scheme_details"]}
    for field, value in values.items():
        setattr(obj, field, value)
    await db.commit()
    after = (await beneficiary_rows(db, [await get_beneficiary_or_404(db, obj.id)]))[0]
    keys = ("voter_id", "name", "scheme", "mandal", "village", "amount", "status")
    await log_activity(
        db, actor_id=current_user.id, action_type="beneficiary_updated", module="beneficiaries", reference_id=obj.id,
        description=f"Updated beneficiary {after['id']} ({after['name']})",
        changes=[[k, str(before[k] or "—"), str(after[k] or "—")] for k in keys if before[k] != after[k]],
        commit=True,
    )
    return after


@router.post(
    "/bulk-upload",
    response_model=BulkImportResult,
    summary="Bulk-import beneficiaries",
    description=(
        "Either a CSV / single-sheet file with columns Voter ID, Name, Scheme, Mandal, Village, Amount, Status "
        "(extra columns are kept as scheme details), or the older .xlsx workbook with one tab per scheme_code: "
        + ", ".join(SCHEME_REGISTRY) + ". All-or-nothing."
    ),
)
async def bulk_upload_beneficiaries(file: UploadFile, db: DbSession, current_user: CanEdit) -> BulkImportResult:
    name = (file.filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        sheets = await parse_excel_workbook(file)
        if sheets and set(sheets) <= set(SCHEME_REGISTRY):
            result = await bulk_import_all_beneficiaries(db, sheets, actor_id=current_user.id)
            if result.errors:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(result.errors))
            return result
        await file.seek(0)
    rows = await parse_upload_rows(
        file, required_columns={"voter_id", "name", "scheme", "mandal", "village"}, aliases=BENEFICIARY_HEADER_ALIASES
    )
    errors: list[BulkImportRowError] = []
    mandal_map, village_map, _ = await load_geography_maps(db)
    ready = []
    for raw in rows:
        row_num = raw["_row_number"]
        clean = {k: v for k, v in raw.items() if not k.startswith("_")}
        try:
            form = BeneficiaryForm.model_validate(clean)
            scheme = await find_scheme(db, form.scheme)
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
            errors.append(BulkImportRowError(row=row_num, epic_no=str(raw.get("voter_id") or "") or None, reason=reason))
            continue
        except HTTPException as exc:
            errors.append(BulkImportRowError(row=row_num, epic_no=str(raw.get("voter_id")), reason=exc.detail))
            continue
        mandal_id = mandal_map.get(form.mandal.lower())
        village_id = village_map.get((mandal_id, form.village.lower())) if mandal_id else None
        if mandal_id is None or village_id is None:
            errors.append(BulkImportRowError(row=row_num, epic_no=form.voter_id, reason=f"Unknown mandal/village '{form.mandal}' / '{form.village}'"))
            continue
        ready.append((form, scheme, mandal_id, village_id))
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=capped_error_detail(errors))
    epics = [f.voter_id for f, *_ in ready]
    voters = {v.epic_no: v for v in (await db.execute(select(Voter).where(Voter.epic_no.in_(epics or ["-"])))).scalars().all()}
    for form, scheme, mandal_id, village_id in ready:
        voter = voters.get(form.voter_id)
        db.add(
            Beneficiary(
                scheme_id=scheme.id, voter_id=voter.id if voter else None, epic_no=form.voter_id,
                beneficiary_name=form.name, mandal_id=mandal_id, village_id=village_id,
                amount=form.amount if form.amount is not None else scheme.amount_per_beneficiary,
                status=form.status, mobile_number=form.mobile or (voter.mobile if voter else None),
                scheme_details=form.extras(), created_by=current_user.id,
            )
        )
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="beneficiary_bulk_imported", module="beneficiaries",
        reference_id=None, description=f"Bulk import: {len(ready)} beneficiaries added",
    )
    await db.commit()
    return BulkImportResult(inserted=len(ready), errors=[])


@router.get(
    "/bulk-upload/template",
    summary="Download the all-schemes beneficiaries workbook template (.xlsx)",
    description=(
        "One tab per scheme, named by scheme_code. Tabs are header-only (hover a header for its rule): "
        "fill the tabs you need and leave the rest empty — empty tabs are skipped by the upload."
    ),
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
async def download_all_schemes_template(db: DbSession, current_user: CanEdit) -> Response:
    mandals = await mandal_names(db)
    specs = [
        TemplateSheet(title=code, columns=columns_from_schema(bulk_row_schema(schema), mandals))
        for code, (schema, _) in SCHEME_REGISTRY.items()
    ]
    return Response(
        content=build_multi_sheet_template(specs),
        media_type=XLSX_MEDIA_TYPE,
        headers=xlsx_attachment_headers("beneficiaries_all_schemes_template.xlsx"),
    )


@router.get(
    "/lookup/{epic_no}",
    response_model=list[BeneficiaryLookupResult],
    summary="Beneficiary Lookup — every scheme this EPIC appears in",
)
async def beneficiary_lookup(epic_no: str, db: DbSession, current_user: CanView) -> list[BeneficiaryLookupResult]:
    stmt = (
        select(Beneficiary, Scheme.scheme_name)
        .join(Scheme, Scheme.id == Beneficiary.scheme_id)
        .where(Beneficiary.epic_no == epic_no.upper())
        .order_by(Beneficiary.application_date.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        BeneficiaryLookupResult(scheme_name=scheme_name, amount=b.amount, date=b.application_date, status=b.status)
        for b, scheme_name in rows
    ]


@router.get(
    "/by-geography",
    response_model=list[BeneficiaryGeographyRow],
    summary="Beneficiaries by mandal/village across every scheme (v_beneficiaries_by_geography)",
)
async def beneficiaries_by_geography(db: DbSession, current_user: CanView) -> list[BeneficiaryGeographyRow]:
    result = await db.execute(
        text(
            "SELECT mandal_name, village_name, scheme_name, status, beneficiary_count, total_amount "
            "FROM v_beneficiaries_by_geography ORDER BY mandal_name, village_name, scheme_name"
        )
    )
    return [BeneficiaryGeographyRow(**row._mapping) for row in result]


@router.get("/{beneficiary_id}", summary="Get one beneficiary (any scheme)")
async def get_beneficiary(beneficiary_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    obj = await get_beneficiary_or_404(db, parse_id(beneficiary_id, label="Beneficiary"))
    return (await beneficiary_rows(db, [obj]))[0]


@router.delete("/{beneficiary_id}", summary="Delete a beneficiary (any scheme)")
async def delete_beneficiary(beneficiary_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await get_beneficiary_or_404(db, parse_id(beneficiary_id, label="Beneficiary"))
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="beneficiary_deleted",
        module="beneficiaries",
        reference_id=obj.id,
        description=f"Deleted beneficiary {obj.beneficiary_name} ({obj.epic_no})",
    )
    await db.delete(obj)
    await db.commit()
    return {"success": True}


@router.get("/{beneficiary_id}/aadhaar/reveal", summary="Reveal a beneficiary's plaintext Aadhaar (super_admin only)")
async def reveal_beneficiary_aadhaar(
    beneficiary_id: str, db: DbSession, current_user: RequireSuperAdmin
) -> dict[str, str | None]:
    obj = await get_beneficiary_or_404(db, parse_id(beneficiary_id, label="Beneficiary"))
    return {"aadhaar_number": decrypt_aadhaar(obj.aadhaar_number) if obj.aadhaar_number else None}
