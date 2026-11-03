"""Government Offices page (frontend: GovernmentOffices.jsx, OfficeModals.jsx, mockGovernmentOfficesApi).

    GET    /government-offices            getAll()   array (q / mandal / category / type filters)
    GET    /government-offices/summary    cards: total, revenue_admin, hospitals, schools, police_services
    GET    /government-offices/{id}       one office
    POST   /government-offices            create(data)  {name, type, contact_number, mandal, village, address, photo}
    PUT    /government-offices/{id}       update(id, data)
    DELETE /government-offices/{id}       delete(id) -> {"success": true}

Ids are "GO-<n>". `category` is derived from the office type.
"""

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.core.scope import resolve_scope
from app.models.geography import Mandal, Village
from app.models.government_offices import GovernmentOffice
from app.services.activity_service import log_activity
from app.services.geography_service import name_maps, resolve_geography

router = APIRouter(prefix="/government-offices", tags=["Government Offices"])

CanView = page_access("government_offices", "view")
CanEdit = page_access("government_offices", "edit")
CanDelete = page_access("government_offices", "admin")

PREFIX = "GO"
OFFICE_TYPES = [
    "MRO / Tahsildar Office",
    "Primary Health Centre (PHC)",
    "Government School",
    "Agriculture Office",
    "VRO office",
    "Sports campus",
    "MPDO Office",
    "Police Station",
    "Electricity (APCPDCL) Office",
    "Postal Office",
]
CATEGORIES = ("revenue_admin", "hospitals", "schools", "police_services")


def category_for(office_type: str) -> str:
    """Same rule as the dashboard: health -> hospitals, school/sports/hostel -> schools,
    police/electricity/postal -> police_services, everything else -> revenue_admin."""
    t = office_type.lower()
    if "health" in t or "phc" in t or "hospital" in t:
        return "hospitals"
    if "school" in t or "sports" in t or "hostel" in t or "college" in t:
        return "schools"
    if "police" in t or "electricity" in t or "postal" in t:
        return "police_services"
    return "revenue_admin"


class OfficeForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=100)
    contact_number: str
    mandal: str
    village: str
    address: str = Field(min_length=1)
    photo: str | None = None
    name_te: str | None = None
    type_te: str | None = None
    address_te: str | None = None

    @field_validator("name", "type", "mandal", "village", "address", "photo", "name_te", "type_te", "address_te", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("contact_number", mode="before")
    @classmethod
    def _contact(cls, v: object) -> str:
        text = re.sub(r"[\s-]", "", str(v or ""))
        if not re.fullmatch(r"\+?\d{6,15}", text):
            raise ValueError("contact_number must be 6-15 digits")
        return text


def office_row(o: GovernmentOffice, mandals: dict[int, str], villages: dict[int, str]) -> dict[str, Any]:
    return {
        "id": format_id(PREFIX, o.id),
        "name": o.name,
        "type": o.office_type,
        "category": o.category,
        "mandal": mandals.get(o.mandal_id),
        "village": villages.get(o.village_id),
        "address": o.address,
        "contact_number": o.contact_number,
        "photo": o.photo_url or "",
        "name_te": o.name_te,
        "type_te": o.type_te,
        "address_te": o.address_te,
        "createdAt": o.created_at,
        "updatedAt": o.updated_at,
    }


async def office_rows(db, offices: list[GovernmentOffice]) -> list[dict[str, Any]]:
    mandals, villages = await name_maps(db, {o.mandal_id for o in offices}, {o.village_id for o in offices})
    return [office_row(o, mandals, villages) for o in offices]


async def _get(db, office_id: str) -> GovernmentOffice:
    obj = await db.get(GovernmentOffice, parse_id(office_id, label="Office"), populate_existing=True)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Office not found")
    return obj


async def _apply(db, obj: GovernmentOffice, form: OfficeForm) -> None:
    obj.mandal_id, obj.village_id = await resolve_geography(db, mandal_name=form.mandal, village_name=form.village)
    obj.name = form.name
    obj.office_type = form.type
    obj.category = category_for(form.type)
    obj.contact_number = form.contact_number
    obj.address = form.address
    obj.photo_url = form.photo
    obj.name_te = form.name_te
    obj.type_te = form.type_te
    obj.address_te = form.address_te


@router.get("/types", summary="Office types offered in the form")
async def office_types(current_user: CanView) -> list[str]:
    return OFFICE_TYPES


@router.get("", summary="List government offices")
async def list_offices(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None),
    mandal: str | None = Query(None),
    category: str | None = Query(None, pattern="^(revenue_admin|hospitals|schools|police_services)$"),
    office_type: str | None = Query(None, alias="type"),
) -> list[dict[str, Any]]:
    stmt = (
        select(GovernmentOffice)
        .join(Mandal, Mandal.id == GovernmentOffice.mandal_id)
        .join(Village, Village.id == GovernmentOffice.village_id)
    )
    stmt = (await resolve_scope(db, current_user)).apply(stmt, mandal_col=GovernmentOffice.mandal_id)
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if category:
        stmt = stmt.where(GovernmentOffice.category == category)
    if office_type:
        stmt = stmt.where(GovernmentOffice.office_type == office_type)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                GovernmentOffice.name.ilike(term),
                GovernmentOffice.office_type.ilike(term),
                GovernmentOffice.address.ilike(term),
                GovernmentOffice.contact_number.ilike(term),
                Mandal.name.ilike(term),
                Village.name.ilike(term),
            )
        )
    offices = list((await db.execute(stmt.order_by(GovernmentOffice.id.desc()))).scalars().all())
    return await office_rows(db, offices)


@router.get("/summary", summary="Government Offices summary cards")
async def offices_summary(db: DbSession, current_user: CanView) -> dict[str, int]:
    stmt = select(GovernmentOffice.category, func.count()).group_by(GovernmentOffice.category)
    stmt = (await resolve_scope(db, current_user)).apply(stmt, mandal_col=GovernmentOffice.mandal_id)
    counts = dict((await db.execute(stmt)).all())
    return {"total": sum(counts.values()), **{c: counts.get(c, 0) for c in CATEGORIES}}


@router.get("/{office_id}", summary="Get one office")
async def get_office(office_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    return (await office_rows(db, [await _get(db, office_id)]))[0]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a government office")
async def create_office(payload: OfficeForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = GovernmentOffice()
    await _apply(db, obj, payload)
    db.add(obj)
    await db.flush()
    await log_activity(
        db, actor_id=current_user.id, action_type="office_added", module="Government Offices",
        reference_id=obj.id, description=f"Added office {obj.name} ({obj.office_type})",
    )
    await db.commit()
    return (await office_rows(db, [await _get(db, str(obj.id))]))[0]


@router.put("/{office_id}", summary="Update a government office")
async def update_office(office_id: str, payload: OfficeForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, office_id)
    before = (await office_rows(db, [obj]))[0]
    await _apply(db, obj, payload)
    await db.commit()
    after = (await office_rows(db, [await _get(db, office_id)]))[0]
    keys = ("name", "type", "mandal", "village", "address", "contact_number")
    await log_activity(
        db, actor_id=current_user.id, action_type="office_updated", module="Government Offices",
        reference_id=obj.id, description=f"Updated office {after['name']}",
        changes=[[k, str(before[k] or "—"), str(after[k] or "—")] for k in keys if before[k] != after[k]],
        commit=True,
    )
    return after


@router.delete("/{office_id}", summary="Delete a government office")
async def delete_office(office_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, office_id)
    await log_activity(
        db, actor_id=current_user.id, action_type="office_deleted", module="Government Offices",
        reference_id=obj.id, description=f"Deleted office {obj.name}",
    )
    await db.delete(obj)
    await db.commit()
    return {"success": True}
