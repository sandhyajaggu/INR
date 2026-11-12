"""Mandals and villages — dropdown lists plus full CRUD, with Telugu names.

    GET    /mandals                          [{id, name, name_te, village_count}]
    GET    /mandals/{id}                     one mandal
    POST   /mandals                          {name, name_te}
    PUT    /mandals/{id}                     {name?, name_te?}
    DELETE /mandals/{id}                     409 if villages / voters / booths still use it

    GET    /villages?mandal_name=Kandukur    [{id, name, name_te, mandal_id, mandal, mandal_te}]
           (or ?mandal_id=1; no filter = every village)
    GET    /villages/{id}                    one village
    POST   /villages                         {mandal (name) or mandal_id, name, name_te}
    PUT    /villages/{id}                    {name?, name_te?, mandal?/mandal_id? (move)}
    DELETE /villages/{id}                    409 if voters / booths / ... still use it

    GET    /public/mandals, /public/villages same lists without login (public website forms);
                                         ?lang=te -> "name" is Telugu, English kept in "name_en"

Reads need any login; add/edit need Settings "edit"; delete needs Settings "admin".
`name` is unchanged from before, so existing dropdown code keeps working.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import CurrentUser, DbSession, page_access
from app.core.ids import parse_id
from app.core.telugu import LangQuery, localize_all
from app.models.geography import Mandal, Village
from app.models.staff import StaffUser
from app.services.activity_service import log_activity

router = APIRouter(tags=["Geography"])
public_router = APIRouter(prefix="/public", tags=["Public"])

CanEdit = page_access("settings", "edit")
CanDelete = page_access("settings", "admin")


def _clean(v: object) -> object:
    if isinstance(v, str):
        v = " ".join(v.split())
        return v or None
    return v


class MandalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    name_te: str | None = Field(default=None, max_length=150)

    strip_text = field_validator("name", "name_te", mode="before")(_clean)


class MandalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    name_te: str | None = Field(default=None, max_length=150)

    strip_text = field_validator("name", "name_te", mode="before")(_clean)


class VillageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    name_te: str | None = Field(default=None, max_length=150)
    mandal: str | None = Field(default=None, description="Mandal name (or send mandal_id)")
    mandal_id: int | str | None = None

    strip_text = field_validator("name", "name_te", "mandal", mode="before")(_clean)


class VillageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    name_te: str | None = Field(default=None, max_length=150)
    mandal: str | None = None
    mandal_id: int | str | None = None

    strip_text = field_validator("name", "name_te", "mandal", mode="before")(_clean)


# --- helpers -----------------------------------------------------------------

def _mandal_out(m: Mandal, village_count: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"id": m.id, "name": m.name, "name_te": m.name_te, "created_at": m.created_at}
    if village_count is not None:
        out["village_count"] = village_count
    return out


def _village_out(v: Village, m: Mandal) -> dict[str, Any]:
    return {
        "id": v.id, "name": v.name, "name_te": v.name_te,
        "mandal_id": m.id, "mandal": m.name, "mandal_te": m.name_te, "created_at": v.created_at,
    }


async def _mandal_by_name(db, name: str) -> Mandal | None:
    return (
        await db.execute(select(Mandal).where(func.lower(Mandal.name) == name.strip().lower()))
    ).scalar_one_or_none()


async def _get_mandal(db, mandal_id: str | int) -> Mandal:
    m = await db.get(Mandal, parse_id(mandal_id, label="Mandal"))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mandal not found")
    return m


async def _get_village(db, village_id: str | int) -> Village:
    v = await db.get(Village, parse_id(village_id, label="Village"))
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Village not found")
    return v


async def _resolve_mandal(db, name: str | None, mandal_id: int | str | None) -> Mandal | None:
    if mandal_id not in (None, ""):
        return await _get_mandal(db, mandal_id)
    if name:
        m = await _mandal_by_name(db, name)
        if m is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown mandal '{name}'")
        return m
    return None


async def _list_mandals(db) -> list[dict[str, Any]]:
    counts = dict(
        (await db.execute(select(Village.mandal_id, func.count()).group_by(Village.mandal_id))).all()
    )
    mandals = (await db.execute(select(Mandal).order_by(Mandal.name))).scalars().all()
    return [_mandal_out(m, counts.get(m.id, 0)) for m in mandals]


async def _list_villages(db, mandal_name: str | None, mandal_id: int | str | None) -> list[dict[str, Any]]:
    stmt = select(Village, Mandal).join(Mandal, Village.mandal_id == Mandal.id)
    if mandal_name is not None or mandal_id is not None:
        m = await _resolve_mandal(db, mandal_name, mandal_id)
        if m is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown mandal '{mandal_name}'")
        stmt = stmt.where(Village.mandal_id == m.id)
    rows = (await db.execute(stmt.order_by(Mandal.name, Village.name))).all()
    return [_village_out(v, m) for v, m in rows]


async def _commit_or_409(db, message: str, *, flush_only: bool = False) -> None:
    try:
        await (db.flush() if flush_only else db.commit())
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, message) from None


# --- mandals -----------------------------------------------------------------

@router.get("/mandals", summary="List mandals (with Telugu names)")
async def list_mandals(db: DbSession, current_user: CurrentUser) -> list[dict[str, Any]]:
    return await _list_mandals(db)


@router.get("/mandals/{mandal_id}", summary="One mandal")
async def get_mandal(mandal_id: str, db: DbSession, current_user: CurrentUser) -> dict[str, Any]:
    m = await _get_mandal(db, mandal_id)
    count = (await db.execute(select(func.count()).select_from(Village).where(Village.mandal_id == m.id))).scalar_one()
    return _mandal_out(m, count)


@router.post("/mandals", status_code=status.HTTP_201_CREATED, summary="Add a mandal")
async def create_mandal(payload: MandalCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    if await _mandal_by_name(db, payload.name):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mandal '{payload.name}' already exists")
    m = Mandal(name=payload.name, name_te=payload.name_te)
    db.add(m)
    await db.flush()
    await log_activity(db, actor_id=current_user.id, action_type="mandal_added", module="Settings",
                       reference_id=m.id, description=f"Added mandal {m.name}")
    await _commit_or_409(db, f"Mandal '{payload.name}' already exists")
    await db.refresh(m)
    return _mandal_out(m, 0)


@router.put("/mandals/{mandal_id}", summary="Rename a mandal / set its Telugu name")
async def update_mandal(mandal_id: str, payload: MandalUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    m = await _get_mandal(db, mandal_id)
    data = payload.model_dump(exclude_unset=True)
    old_name = m.name
    if data.get("name") and data["name"].lower() != m.name.lower():
        if await _mandal_by_name(db, data["name"]):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Mandal '{data['name']}' already exists")
    if data.get("name"):
        m.name = data["name"]
    if "name_te" in data:
        m.name_te = data["name_te"]
    if m.name != old_name:
        # Staff scope (Mandal In-Charge etc.) is stored by name — keep it pointing at this mandal.
        await db.execute(update(StaffUser).where(StaffUser.mandal == old_name).values(mandal=m.name))
    await log_activity(db, actor_id=current_user.id, action_type="mandal_updated", module="Settings",
                       reference_id=m.id, description=f"Updated mandal {old_name}" + (f" → {m.name}" if m.name != old_name else ""))
    await _commit_or_409(db, f"Mandal '{m.name}' already exists")
    return await get_mandal(str(m.id), db, current_user)


@router.delete("/mandals/{mandal_id}", summary="Delete an unused mandal")
async def delete_mandal(mandal_id: str, db: DbSession, current_user: CanDelete) -> dict[str, bool]:
    m = await _get_mandal(db, mandal_id)
    villages = (await db.execute(select(func.count()).select_from(Village).where(Village.mandal_id == m.id))).scalar_one()
    if villages:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mandal '{m.name}' still has {villages} villages; delete or move them first")
    name, ref = m.name, m.id
    await db.delete(m)
    await _commit_or_409(db, f"Mandal '{name}' is in use (voters, booths or other records) and cannot be deleted",
                         flush_only=True)
    await log_activity(db, actor_id=current_user.id, action_type="mandal_deleted", module="Settings",
                       reference_id=ref, description=f"Deleted mandal {name}")
    await db.commit()
    return {"success": True}


# --- villages ----------------------------------------------------------------

@router.get("/villages", summary="List villages (optionally of one mandal), with Telugu names")
async def list_villages(
    db: DbSession,
    current_user: CurrentUser,
    mandal_name: str | None = Query(None, description="Mandal name, e.g. Kandukur"),
    mandal_id: int | None = Query(None),
) -> list[dict[str, Any]]:
    return await _list_villages(db, mandal_name, mandal_id)


@router.get("/villages/{village_id}", summary="One village")
async def get_village(village_id: str, db: DbSession, current_user: CurrentUser) -> dict[str, Any]:
    v = await _get_village(db, village_id)
    return _village_out(v, await db.get(Mandal, v.mandal_id))


async def _village_exists(db, mandal_id: int, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Village.id).where(Village.mandal_id == mandal_id, func.lower(Village.name) == name.lower())
    if exclude_id:
        stmt = stmt.where(Village.id != exclude_id)
    return (await db.execute(stmt)).first() is not None


@router.post("/villages", status_code=status.HTTP_201_CREATED, summary="Add a village to a mandal")
async def create_village(payload: VillageCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    m = await _resolve_mandal(db, payload.mandal, payload.mandal_id)
    if m is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Send 'mandal' (name) or 'mandal_id'")
    if await _village_exists(db, m.id, payload.name):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Village '{payload.name}' already exists in {m.name}")
    v = Village(mandal_id=m.id, name=payload.name, name_te=payload.name_te)
    db.add(v)
    await db.flush()
    await log_activity(db, actor_id=current_user.id, action_type="village_added", module="Settings",
                       reference_id=v.id, description=f"Added village {v.name} ({m.name})")
    await _commit_or_409(db, f"Village '{payload.name}' already exists in {m.name}")
    await db.refresh(v)
    return _village_out(v, m)


@router.put("/villages/{village_id}", summary="Rename a village, set its Telugu name, or move it")
async def update_village(village_id: str, payload: VillageUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    v = await _get_village(db, village_id)
    old_mandal = await db.get(Mandal, v.mandal_id)
    data = payload.model_dump(exclude_unset=True)
    target = await _resolve_mandal(db, data.get("mandal"), data.get("mandal_id")) or old_mandal
    new_name = data.get("name") or v.name
    if await _village_exists(db, target.id, new_name, exclude_id=v.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Village '{new_name}' already exists in {target.name}")
    old_name = v.name
    v.name, v.mandal_id = new_name, target.id
    if "name_te" in data:
        v.name_te = data["name_te"]
    if old_name != v.name or old_mandal.id != target.id:
        await db.execute(
            update(StaffUser)
            .where(StaffUser.village == old_name, StaffUser.mandal == old_mandal.name)
            .values(village=v.name, mandal=target.name)
        )
    await log_activity(db, actor_id=current_user.id, action_type="village_updated", module="Settings",
                       reference_id=v.id, description=f"Updated village {old_name} ({old_mandal.name})")
    await _commit_or_409(db, f"Village '{new_name}' already exists in {target.name}")
    await db.refresh(v)
    return _village_out(v, target)


@router.delete("/villages/{village_id}", summary="Delete an unused village")
async def delete_village(village_id: str, db: DbSession, current_user: CanDelete) -> dict[str, bool]:
    v = await _get_village(db, village_id)
    name, ref = v.name, v.id
    await db.delete(v)
    await _commit_or_409(db, f"Village '{name}' is in use (voters, booths or other records) and cannot be deleted",
                         flush_only=True)
    await log_activity(db, actor_id=current_user.id, action_type="village_deleted", module="Settings",
                       reference_id=ref, description=f"Deleted village {name}")
    await db.commit()
    return {"success": True}


# --- public (no login) -------------------------------------------------------

@public_router.get("/mandals", summary="Mandals for public website forms (unauthenticated); ?lang=te for Telugu")
async def public_mandals(db: DbSession, lang: LangQuery = "en") -> list[dict[str, Any]]:
    rows = [{"id": m["id"], "name": m["name"], "name_te": m["name_te"]} for m in await _list_mandals(db)]
    return localize_all(rows, lang, ("name",))


@public_router.get("/villages", summary="Villages for public website forms (unauthenticated); ?lang=te for Telugu")
async def public_villages(
    db: DbSession,
    lang: LangQuery = "en",
    mandal_name: str | None = Query(None, description="Mandal name in English or Telugu"),
    mandal_id: int | None = Query(None),
) -> list[dict[str, Any]]:
    if mandal_name:
        te_match = (await db.execute(select(Mandal.name).where(Mandal.name_te == mandal_name.strip()))).scalar_one_or_none()
        mandal_name = te_match or mandal_name
    rows = [
        {"id": v["id"], "name": v["name"], "name_te": v["name_te"], "mandal": v["mandal"], "mandal_te": v["mandal_te"]}
        for v in await _list_villages(db, mandal_name, mandal_id)
    ]
    return localize_all(rows, lang, ("name", "mandal"))
