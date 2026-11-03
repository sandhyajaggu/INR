"""Government Schemes page (frontend: GovernmentSchemes.jsx, mockSchemesApi).

    GET    /schemes          getAll()   array of schemes with beneficiaries_count, amount_paid, disbursed_pct
    GET    /schemes/{id}     one scheme
    POST   /schemes          create(data)
    PUT    /schemes/{id}     update(id, data)
    DELETE /schemes/{id}     delete(id) -> {"success": true}  (only when it has no beneficiaries)

Ids are "SCH-<n>". CMRF has its own page, so it is left out of the list
unless include_cmrf=true.
"""

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.models.schemes import Beneficiary, Scheme
from app.schemas.schemes import SchemeCreate, SchemeUpdate
from app.services.activity_service import log_activity

router = APIRouter(prefix="/schemes", tags=["Government Schemes"])

CanView = page_access("government_schemes", "view")
CanEdit = page_access("government_schemes", "edit")
CanDelete = page_access("government_schemes", "admin")

PREFIX = "SCH"
CMRF_CODE = "cmrf"


def tags_of(extra_details: str | None) -> list[str]:
    return [t.strip() for t in (extra_details or "").split(",") if t.strip()]


def short_code_for(name: str) -> str:
    initials = "".join(w[0] for w in name.split() if w and w[0].isalnum())[:2].upper()
    return initials or "GS"


def slug_for(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:45] or "scheme"


async def scheme_totals(db) -> dict[int, dict[str, float]]:
    stmt = select(
        Beneficiary.scheme_id,
        func.count(),
        func.coalesce(func.sum(Beneficiary.amount).filter(Beneficiary.status == "disbursed"), 0),
        func.count().filter(Beneficiary.status == "disbursed"),
    ).group_by(Beneficiary.scheme_id)
    return {
        sid: {"count": n, "paid": float(paid), "disbursed": d} for sid, n, paid, d in (await db.execute(stmt)).all()
    }


def scheme_row(s: Scheme, totals: dict[str, float] | None) -> dict[str, Any]:
    t = totals or {"count": 0, "paid": 0.0, "disbursed": 0}
    return {
        "id": format_id(PREFIX, s.id),
        "code": s.short_code or short_code_for(s.scheme_name),
        "scheme_code": s.scheme_code,
        "name": s.scheme_name,
        "telugu_name": s.telugu_name,
        "department": s.department,
        "frequency": s.frequency,
        "benefit": s.benefit,
        "amount_per_beneficiary": float(s.amount_per_beneficiary) if s.amount_per_beneficiary is not None else 0,
        "status": "Active" if s.status == "active" else "Inactive",
        "extra_details": s.extra_details or "",
        "tags": tags_of(s.extra_details),
        "other_spellings": s.other_spellings or "",
        "description": s.short_description,
        "beneficiaries_count": t["count"],
        "amount_paid": t["paid"],
        "disbursed_pct": round(t["disbursed"] * 100 / t["count"]) if t["count"] else 0,
        "createdAt": s.created_at,
    }


async def _get(db, scheme_id: str) -> Scheme:
    obj = await db.get(Scheme, parse_id(scheme_id, label="Scheme"), populate_existing=True)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheme not found")
    return obj


def _apply(obj: Scheme, payload: SchemeCreate) -> None:
    obj.scheme_name = payload.name.strip()
    obj.telugu_name = payload.telugu_name
    obj.department = payload.department
    obj.frequency = payload.frequency
    obj.benefit = payload.benefit
    obj.amount_per_beneficiary = payload.amount_per_beneficiary
    obj.status = payload.status.lower()
    obj.extra_details = payload.extra_details
    obj.other_spellings = payload.other_spellings
    obj.short_description = payload.description
    obj.short_code = short_code_for(obj.scheme_name) if not obj.short_code else obj.short_code


async def _ensure_unique_name(db, name: str, exclude_id: int | None = None) -> None:
    stmt = select(Scheme.id).where(func.lower(Scheme.scheme_name) == name.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(Scheme.id != exclude_id)
    if (await db.execute(stmt)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"A scheme named '{name}' already exists")


@router.get("", summary="List government schemes")
async def list_schemes(
    db: DbSession,
    current_user: CanView,
    include_cmrf: bool = Query(False),
    status_filter: str | None = Query(None, alias="status", pattern="^(Active|Inactive)$"),
) -> list[dict[str, Any]]:
    stmt = select(Scheme).order_by(Scheme.id)
    if not include_cmrf:
        stmt = stmt.where(Scheme.scheme_code != CMRF_CODE)
    if status_filter:
        stmt = stmt.where(Scheme.status == status_filter.lower())
    totals = await scheme_totals(db)
    return [scheme_row(s, totals.get(s.id)) for s in (await db.execute(stmt)).scalars().all()]


@router.get("/{scheme_id}", summary="Get one scheme")
async def get_scheme(scheme_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    obj = await _get(db, scheme_id)
    return scheme_row(obj, (await scheme_totals(db)).get(obj.id))


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a scheme")
async def create_scheme(payload: SchemeCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    await _ensure_unique_name(db, payload.name)
    code = slug_for(payload.name)
    if (await db.execute(select(Scheme.id).where(Scheme.scheme_code == code))).first():
        code = f"{code}_{(await db.execute(select(func.count()).select_from(Scheme))).scalar_one() + 1}"
    obj = Scheme(scheme_code=code, scheme_name=payload.name)
    _apply(obj, payload)
    db.add(obj)
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="scheme_added", module="Government Schemes",
        reference_id=obj.id, description=f"Added scheme {obj.scheme_name}",
    )
    await db.commit()
    return scheme_row(await _get(db, str(obj.id)), None)


@router.put("/{scheme_id}", summary="Update a scheme")
async def update_scheme(scheme_id: str, payload: SchemeUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, scheme_id)
    await _ensure_unique_name(db, payload.name, exclude_id=obj.id)
    before = scheme_row(obj, None)
    _apply(obj, payload)
    after = scheme_row(obj, None)
    keys = ("name", "department", "frequency", "benefit", "amount_per_beneficiary", "status", "extra_details", "other_spellings")
    await log_activity(
        db, actor_id=current_user.id, action_type="scheme_updated", module="Government Schemes",
        reference_id=obj.id, description=f"Updated scheme {obj.scheme_name}",
        changes=[[k, str(before[k] or "—"), str(after[k] or "—")] for k in keys if before[k] != after[k]],
    )
    await db.commit()
    return scheme_row(await _get(db, scheme_id), (await scheme_totals(db)).get(obj.id))


@router.delete("/{scheme_id}", summary="Delete a scheme (only if it has no beneficiaries)")
async def delete_scheme(scheme_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, scheme_id)
    used = (await db.execute(select(func.count()).select_from(Beneficiary).where(Beneficiary.scheme_id == obj.id))).scalar_one()
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"'{obj.scheme_name}' has {used} beneficiaries. Remove them first, or set the scheme to Inactive.",
        )
    await log_activity(
        db, actor_id=current_user.id, action_type="scheme_deleted", module="Government Schemes",
        reference_id=obj.id, description=f"Deleted scheme {obj.scheme_name}",
    )
    await db.delete(obj)
    await db.commit()
    return {"success": True}
