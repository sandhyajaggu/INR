"""Beneficiaries — cross-scheme read/search/delete over the single shared
`beneficiaries` table. Create/update now live on each scheme's own router
(app/api/routes/beneficiaries_<scheme>.py) since each scheme has genuinely
different Add/Edit form fields — see app/core/beneficiary_scheme_router.py.
This router keeps only what's inherently cross-scheme: listing across all
schemes, the Beneficiary Lookup (every scheme one EPIC appears in), the
by-geography aggregate, delete-by-id, and the Aadhaar reveal.
"""

from math import ceil

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, text

from app.core.dependencies import CurrentUser, DbSession, RequireStaff, RequireSuperAdmin
from app.models.schemes import Beneficiary, Scheme
from app.schemas.beneficiaries import BeneficiaryGeographyRow, BeneficiaryLookupResult, BeneficiaryOut
from app.schemas.bulk_import import BulkImportResult
from app.schemas.common import PaginatedResponse
from app.services.activity_service import log_activity
from app.services.beneficiary_service import (
    SCHEME_REGISTRY,
    bulk_import_all_beneficiaries,
    get_beneficiary_or_404,
)
from app.services.encryption_service import decrypt_aadhaar, mask_aadhaar
from app.services.excel_import_service import parse_excel_workbook

router = APIRouter(prefix="/beneficiaries", tags=["Beneficiaries"])


def _to_out(obj: Beneficiary) -> BeneficiaryOut:
    return BeneficiaryOut(
        id=obj.id,
        scheme_id=obj.scheme_id,
        voter_id=obj.voter_id,
        epic_no=obj.epic_no,
        beneficiary_name=obj.beneficiary_name,
        relation_name=obj.relation_name,
        age=obj.age,
        gender=obj.gender,
        aadhaar_masked=mask_aadhaar(obj.aadhaar_number),
        mobile_number=obj.mobile_number,
        bank_account_number=obj.bank_account_number,
        ifsc_code=obj.ifsc_code,
        amount=obj.amount,
        village_id=obj.village_id,
        mandal_id=obj.mandal_id,
        application_date=obj.application_date,
        status=obj.status,
        photo_url=obj.photo_url,
        document_url=obj.document_url,
        video_url=obj.video_url,
        remarks=obj.remarks,
        scheme_details=obj.scheme_details,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@router.get(
    "", response_model=PaginatedResponse[BeneficiaryOut], summary="List/filter beneficiaries across all schemes"
)
async def list_beneficiaries(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    scheme_id: int | None = Query(None),
    scheme_code: str | None = Query(None, description="Alternative to scheme_id"),
    mandal_id: int | None = Query(None),
    village_id: int | None = Query(None),
    status: str | None = Query(None),
) -> PaginatedResponse[BeneficiaryOut]:
    stmt = select(Beneficiary)
    count_stmt = select(func.count()).select_from(Beneficiary)
    conditions = []

    if scheme_code and scheme_id is None:
        scheme = (
            await db.execute(select(Scheme.id).where(Scheme.scheme_code == scheme_code))
        ).scalar_one_or_none()
        if scheme is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown scheme_code '{scheme_code}'")
        scheme_id = scheme

    if scheme_id is not None:
        conditions.append(Beneficiary.scheme_id == scheme_id)
    if mandal_id is not None:
        conditions.append(Beneficiary.mandal_id == mandal_id)
    if village_id is not None:
        conditions.append(Beneficiary.village_id == village_id)
    if status:
        conditions.append(Beneficiary.status == status)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Beneficiary.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return PaginatedResponse(
        items=[_to_out(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if page_size else 0,
    )


@router.post(
    "/bulk-upload",
    response_model=BulkImportResult,
    summary="Bulk-import beneficiaries across all schemes from one Excel workbook",
    description=(
        "Upload a single .xlsx workbook with one sheet tab per scheme — the tab "
        "name must be that scheme's scheme_code: " + ", ".join(SCHEME_REGISTRY) + ". "
        "Each sheet is validated against that scheme's own field rules (same as "
        "its single-scheme /beneficiaries/{scheme}/bulk-upload endpoint). "
        "All-or-nothing: if any row in any sheet fails, nothing is written."
    ),
)
async def bulk_upload_all_beneficiaries(
    file: UploadFile, db: DbSession, current_user: RequireStaff
) -> BulkImportResult:
    sheets = await parse_excel_workbook(file)
    result = await bulk_import_all_beneficiaries(db, sheets, actor_id=current_user.id)
    if result.errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=[e.model_dump() for e in result.errors]
        )
    return result


@router.get(
    "/lookup/{epic_no}",
    response_model=list[BeneficiaryLookupResult],
    summary="Beneficiary Lookup — every scheme this EPIC appears in",
)
async def beneficiary_lookup(epic_no: str, db: DbSession, current_user: CurrentUser) -> list[BeneficiaryLookupResult]:
    stmt = (
        select(Beneficiary, Scheme.scheme_name)
        .join(Scheme, Scheme.id == Beneficiary.scheme_id)
        .where(Beneficiary.epic_no == epic_no.upper())
        .order_by(Beneficiary.application_date.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        BeneficiaryLookupResult(
            scheme_name=scheme_name, amount=b.amount, date=b.application_date, status=b.status
        )
        for b, scheme_name in rows
    ]


@router.get(
    "/by-geography",
    response_model=list[BeneficiaryGeographyRow],
    summary="Beneficiaries by mandal/village across every scheme (v_beneficiaries_by_geography)",
)
async def beneficiaries_by_geography(db: DbSession, current_user: CurrentUser) -> list[BeneficiaryGeographyRow]:
    result = await db.execute(
        text(
            "SELECT mandal_name, village_name, scheme_name, status, beneficiary_count, total_amount "
            "FROM v_beneficiaries_by_geography ORDER BY mandal_name, village_name, scheme_name"
        )
    )
    return [BeneficiaryGeographyRow(**row._mapping) for row in result]


@router.get("/{beneficiary_id}", response_model=BeneficiaryOut, summary="Get one beneficiary (any scheme)")
async def get_beneficiary(beneficiary_id: int, db: DbSession, current_user: CurrentUser) -> BeneficiaryOut:
    return _to_out(await get_beneficiary_or_404(db, beneficiary_id))


@router.delete(
    "/{beneficiary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a beneficiary (any scheme, super_admin only)",
)
async def delete_beneficiary(
    beneficiary_id: int, db: DbSession, current_user: RequireSuperAdmin
) -> None:
    obj = await get_beneficiary_or_404(db, beneficiary_id)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="beneficiary_deleted",
        module="beneficiaries",
        reference_id=obj.id,
        description=f"Beneficiary '{obj.beneficiary_name}' deleted",
    )
    await db.delete(obj)
    await db.commit()


@router.get(
    "/{beneficiary_id}/aadhaar/reveal",
    summary="Reveal a beneficiary's plaintext Aadhaar (super_admin only)",
)
async def reveal_beneficiary_aadhaar(
    beneficiary_id: int, db: DbSession, current_user: RequireSuperAdmin
) -> dict[str, str | None]:
    obj = await get_beneficiary_or_404(db, beneficiary_id)
    return {"aadhaar_number": decrypt_aadhaar(obj.aadhaar_number) if obj.aadhaar_number else None}
