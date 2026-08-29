from typing import Type

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemes import Beneficiary, Scheme
from app.schemas.beneficiary_schemes import (
    AadabiddaNidhiCreate,
    AnnadataSukhibhavaCreate,
    CmrfCreate,
    DeepamSchemeCreate,
    MahaShakthiCreate,
    ThallikiVandanamCreate,
    YuvagalamCreate,
)
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError
from app.services.activity_service import log_activity
from app.services.encryption_service import encrypt_aadhaar
from app.services.geography_service import load_geography_maps

# scheme_code -> (create_schema, name_field). Kept in sync with the 7
# app/api/routes/beneficiaries_<scheme>.py files, which pass these same
# values to build_beneficiary_scheme_router. Used by the combined
# all-schemes bulk-upload below, where one sheet tab = one scheme_code.
SCHEME_REGISTRY: dict[str, tuple[Type[BaseModel], str]] = {
    "cmrf": (CmrfCreate, "beneficiary_name"),
    "aadabidda_nidhi": (AadabiddaNidhiCreate, "beneficiary_name"),
    "thalliki_vandanam": (ThallikiVandanamCreate, "mother_name"),
    "deepam_scheme": (DeepamSchemeCreate, "head_of_household_name"),
    "maha_shakthi": (MahaShakthiCreate, "beneficiary_name"),
    "annadata_sukhibhava": (AnnadataSukhibhavaCreate, "farmer_name"),
    "yuvagalam": (YuvagalamCreate, "beneficiary_name"),
}


async def link_voter_by_epic(db: AsyncSession, epic_no: str | None) -> int | None:
    if not epic_no:
        return None
    from app.models.voters import Voter

    stmt = select(Voter.id).where(Voter.epic_no == epic_no.upper())
    voter_id = (await db.execute(stmt)).scalar_one_or_none()
    return voter_id


async def get_beneficiary_or_404(db: AsyncSession, beneficiary_id: int) -> Beneficiary:
    obj = await db.get(Beneficiary, beneficiary_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficiary not found")
    return obj


async def bulk_import_all_beneficiaries(
    db: AsyncSession, sheets: dict[str, list[dict]], actor_id: int
) -> BulkImportResult:
    """All-or-nothing bulk import across every beneficiary scheme in one workbook.

    Each sheet tab in the uploaded workbook must be named after a scheme_code
    (e.g. "cmrf", "deepam_scheme" — see SCHEME_REGISTRY); an unrecognized tab
    name is reported as an error rather than silently skipped. Every row in
    every recognized sheet is validated against that scheme's own field rules
    (same as its single-scheme bulk-upload endpoint) before anything is
    written — if any row anywhere in the workbook fails, nothing is inserted.
    """
    from app.core.beneficiary_scheme_router import _split_payload

    errors: list[BulkImportRowError] = []
    for name in sheets:
        if name not in SCHEME_REGISTRY:
            errors.append(
                BulkImportRowError(
                    row=0, reason=f"Unrecognized sheet tab '{name}' — expected one of: {', '.join(SCHEME_REGISTRY)}"
                )
            )

    scheme_ids: dict[str, int] = {}
    for scheme_code in sheets:
        if scheme_code not in SCHEME_REGISTRY:
            continue
        scheme_id = (
            await db.execute(select(Scheme.id).where(Scheme.scheme_code == scheme_code))
        ).scalar_one_or_none()
        if scheme_id is None:
            errors.append(BulkImportRowError(row=0, reason=f"Scheme '{scheme_code}' is not seeded in the database"))
            continue
        scheme_ids[scheme_code] = scheme_id

    mandal_map, village_map, _ = await load_geography_maps(db)
    resolved: list[tuple[str, BaseModel, int, int]] = []
    for scheme_code, rows in sheets.items():
        if scheme_code not in scheme_ids:
            continue
        create_schema, _ = SCHEME_REGISTRY[scheme_code]
        for raw in rows:
            row_num = raw.get("_row_number")
            try:
                parsed = create_schema.model_validate(raw)
            except ValidationError as exc:
                reason = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
                epic_hint = str(raw.get("epic_no") or "").strip().upper() or None
                errors.append(BulkImportRowError(row=row_num, epic_no=epic_hint, reason=f"[{scheme_code}] {reason}"))
                continue

            data = parsed.model_dump()
            epic_hint = data.get("epic_no")
            mandal_id = mandal_map.get(data["mandal_name"].strip().lower())
            if mandal_id is None:
                errors.append(
                    BulkImportRowError(
                        row=row_num, epic_no=epic_hint, reason=f"[{scheme_code}] Unknown mandal_name '{data['mandal_name']}'"
                    )
                )
                continue
            village_id = village_map.get((mandal_id, data["village_name"].strip().lower()))
            if village_id is None:
                errors.append(
                    BulkImportRowError(
                        row=row_num,
                        epic_no=epic_hint,
                        reason=f"[{scheme_code}] Unknown village_name '{data['village_name']}' in mandal '{data['mandal_name']}'",
                    )
                )
                continue
            resolved.append((scheme_code, parsed, mandal_id, village_id))

    if errors:
        return BulkImportResult(inserted=0, errors=errors)

    objs = []
    per_scheme_counts: dict[str, int] = {}
    for scheme_code, parsed, mandal_id, village_id in resolved:
        _, name_field = SCHEME_REGISTRY[scheme_code]
        data = parsed.model_dump()
        data.pop("mandal_name")
        data.pop("village_name")
        core, details = _split_payload(data, name_field)
        if core.get("epic_no"):
            core["epic_no"] = core["epic_no"].upper()
        if core.get("aadhaar_number"):
            core["aadhaar_number"] = encrypt_aadhaar(core["aadhaar_number"])
        voter_id = await link_voter_by_epic(db, core.get("epic_no"))
        objs.append(
            Beneficiary(
                scheme_id=scheme_ids[scheme_code],
                mandal_id=mandal_id,
                village_id=village_id,
                voter_id=voter_id,
                scheme_details=details,
                created_by=actor_id,
                **core,
            )
        )
        per_scheme_counts[scheme_code] = per_scheme_counts.get(scheme_code, 0) + 1

    db.add_all(objs)
    await db.flush()
    summary = ", ".join(f"{count} {code}" for code, count in per_scheme_counts.items())
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="beneficiary_bulk_imported",
        module="beneficiaries",
        reference_id=None,
        description=f"Bulk import: {len(objs)} beneficiaries added ({summary})",
    )
    await db.commit()
    return BulkImportResult(inserted=len(objs), errors=[])
