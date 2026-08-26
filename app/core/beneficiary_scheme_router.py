"""Factory for one scheme's beneficiary CRUD router.

Each of the 7 schemes gets its own router built by this factory — its own
typed Create/Update/Out schema (see app/schemas/beneficiary_schemes.py), but
all of them read/write the single shared `beneficiaries` table (db/schema.sql
is unchanged), pre-filtered to that scheme's scheme_id. A payload field is
routed to one of three places automatically:
  - `name_field` (e.g. "mother_name") -> the beneficiaries.beneficiary_name column
  - any other CORE_BENEFICIARY_COLUMNS name -> that column directly
  - anything else (e.g. student_name, school_name) -> beneficiaries.scheme_details JSONB
"""

from math import ceil
from typing import Any, Type

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.dependencies import CurrentUser, DbSession, RequireStaff, RequireSuperAdmin
from app.models.schemes import Beneficiary, Scheme
from app.schemas.common import PaginatedResponse
from app.services.activity_service import log_activity
from app.services.beneficiary_service import link_voter_by_epic
from app.services.encryption_service import encrypt_aadhaar, mask_aadhaar
from app.services.geography_service import resolve_geography

CORE_BENEFICIARY_COLUMNS = {
    "relation_name", "age", "gender", "aadhaar_number", "mobile_number",
    "bank_account_number", "ifsc_code", "amount", "application_date", "status",
    "photo_url", "document_url", "video_url", "remarks", "epic_no",
}


def _split_payload(data: dict[str, Any], name_field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    core: dict[str, Any] = {}
    details: dict[str, Any] = {}
    for key, value in data.items():
        if key in ("mandal_name", "village_name"):
            continue
        if key == name_field:
            core["beneficiary_name"] = value
        elif key in CORE_BENEFICIARY_COLUMNS:
            core[key] = value
        else:
            details[key] = value
    return core, details


def _to_out(obj: Beneficiary, out_schema: Type[BaseModel], name_field: str) -> Any:
    data = {
        "id": obj.id,
        name_field: obj.beneficiary_name,
        "relation_name": obj.relation_name,
        "epic_no": obj.epic_no,
        "voter_id": obj.voter_id,
        "age": obj.age,
        "aadhaar_masked": mask_aadhaar(obj.aadhaar_number),
        "mobile_number": obj.mobile_number,
        "bank_account_number": obj.bank_account_number,
        "ifsc_code": obj.ifsc_code,
        "amount": obj.amount,
        "mandal_id": obj.mandal_id,
        "village_id": obj.village_id,
        "application_date": obj.application_date,
        "status": obj.status,
        "photo_url": obj.photo_url,
        "document_url": obj.document_url,
        "video_url": obj.video_url,
        "remarks": obj.remarks,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
        **(obj.scheme_details or {}),
    }
    return out_schema(**data)


def _singularize(label: str) -> str:
    if label.endswith("ies"):
        return label[:-3] + "y"
    if label.endswith("s"):
        return label[:-1]
    return label


async def _get_scheme_id(db: DbSession, scheme_code: str) -> int:
    scheme_id = (
        await db.execute(select(Scheme.id).where(Scheme.scheme_code == scheme_code))
    ).scalar_one_or_none()
    if scheme_id is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Scheme '{scheme_code}' is not seeded — run `python -m scripts.seed_schemes`",
        )
    return scheme_id


def build_beneficiary_scheme_router(
    *,
    scheme_code: str,
    prefix: str,
    tags: list[str],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    out_schema: Type[BaseModel],
    resource_label: str,
    name_field: str,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags)

    @router.get("", response_model=PaginatedResponse[out_schema], summary=f"List {resource_label}")
    async def list_items(
        db: DbSession,
        current_user: CurrentUser,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        mandal_id: int | None = Query(None),
        village_id: int | None = Query(None),
        status: str | None = Query(None),
    ) -> Any:
        scheme_id = await _get_scheme_id(db, scheme_code)
        stmt = select(Beneficiary).where(Beneficiary.scheme_id == scheme_id)
        count_stmt = select(func.count()).select_from(Beneficiary).where(Beneficiary.scheme_id == scheme_id)
        for column_name, value in (("mandal_id", mandal_id), ("village_id", village_id), ("status", status)):
            if value is not None:
                stmt = stmt.where(getattr(Beneficiary, column_name) == value)
                count_stmt = count_stmt.where(getattr(Beneficiary, column_name) == value)

        total = (await db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Beneficiary.id.desc()).offset((page - 1) * page_size).limit(page_size)
        items = (await db.execute(stmt)).scalars().all()
        return PaginatedResponse(
            items=[_to_out(i, out_schema, name_field) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if page_size else 0,
        )

    @router.get("/{item_id}", response_model=out_schema, summary=f"Get one {_singularize(resource_label)}")
    async def get_item(item_id: int, db: DbSession, current_user: CurrentUser) -> Any:
        scheme_id = await _get_scheme_id(db, scheme_code)
        obj = await db.get(Beneficiary, item_id)
        if obj is None or obj.scheme_id != scheme_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{_singularize(resource_label)} not found")
        return _to_out(obj, out_schema, name_field)

    @router.post(
        "", response_model=out_schema, status_code=status.HTTP_201_CREATED, summary=f"Add a {_singularize(resource_label)}"
    )
    async def create_item(payload: create_schema, db: DbSession, current_user: RequireStaff) -> Any:  # type: ignore[valid-type]
        scheme_id = await _get_scheme_id(db, scheme_code)
        data = payload.model_dump()
        mandal_id, village_id = await resolve_geography(
            db, mandal_name=data.pop("mandal_name"), village_name=data.pop("village_name")
        )
        core, details = _split_payload(data, name_field)
        if core.get("epic_no"):
            core["epic_no"] = core["epic_no"].upper()
        if core.get("aadhaar_number"):
            core["aadhaar_number"] = encrypt_aadhaar(core["aadhaar_number"])
        voter_id = await link_voter_by_epic(db, core.get("epic_no"))

        obj = Beneficiary(
            scheme_id=scheme_id,
            mandal_id=mandal_id,
            village_id=village_id,
            voter_id=voter_id,
            scheme_details=details,
            created_by=current_user.id,
            **core,
        )
        db.add(obj)
        await db.flush()

        action_type = "cmrf_contribution" if scheme_code == "cmrf" else "beneficiary_added"
        await log_activity(
            db,
            actor_id=current_user.id,
            action_type=action_type,
            module="beneficiaries",
            reference_id=obj.id,
            description=f"{_singularize(resource_label).capitalize()} '{obj.beneficiary_name}' added",
        )
        await db.commit()
        await db.refresh(obj)
        return _to_out(obj, out_schema, name_field)

    @router.put("/{item_id}", response_model=out_schema, summary=f"Update a {_singularize(resource_label)}")
    async def update_item(
        item_id: int, payload: update_schema, db: DbSession, current_user: RequireStaff  # type: ignore[valid-type]
    ) -> Any:
        scheme_id = await _get_scheme_id(db, scheme_code)
        obj = await db.get(Beneficiary, item_id)
        if obj is None or obj.scheme_id != scheme_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{_singularize(resource_label)} not found")

        data = payload.model_dump()
        mandal_id, village_id = await resolve_geography(
            db, mandal_name=data.pop("mandal_name"), village_name=data.pop("village_name")
        )
        core, details = _split_payload(data, name_field)
        if core.get("epic_no"):
            core["epic_no"] = core["epic_no"].upper()
        if core.get("aadhaar_number"):
            core["aadhaar_number"] = encrypt_aadhaar(core["aadhaar_number"])
        obj.voter_id = await link_voter_by_epic(db, core.get("epic_no"))

        obj.mandal_id = mandal_id
        obj.village_id = village_id
        obj.scheme_details = details
        for field, value in core.items():
            setattr(obj, field, value)

        await log_activity(
            db,
            actor_id=current_user.id,
            action_type="beneficiary_updated",
            module="beneficiaries",
            reference_id=obj.id,
            description=f"{_singularize(resource_label).capitalize()} '{obj.beneficiary_name}' updated",
        )
        await db.commit()
        await db.refresh(obj)
        return _to_out(obj, out_schema, name_field)

    @router.delete(
        "/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary=f"Delete a {_singularize(resource_label)} (super_admin only)",
    )
    async def delete_item(item_id: int, db: DbSession, current_user: RequireSuperAdmin) -> None:
        scheme_id = await _get_scheme_id(db, scheme_code)
        obj = await db.get(Beneficiary, item_id)
        if obj is None or obj.scheme_id != scheme_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{_singularize(resource_label)} not found")
        await log_activity(
            db,
            actor_id=current_user.id,
            action_type="beneficiary_deleted",
            module="beneficiaries",
            reference_id=item_id,
            description=f"{_singularize(resource_label).capitalize()} '{obj.beneficiary_name}' deleted",
        )
        await db.delete(obj)
        await db.commit()

    return router
