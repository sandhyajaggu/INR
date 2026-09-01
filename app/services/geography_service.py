"""Resolves human-readable mandal/village names to their internal IDs.

Every create/update request across the API takes mandal_name/village_name
(not numeric IDs) — the DB schema itself is unchanged (still FK'd by ID;
db/schema.sql is source of truth and wasn't touched), this is purely an
API-boundary translation. Village names are only unique within a mandal
(schema.sql's UNIQUE constraint is (mandal_id, name)), so village lookups
are always scoped to an already-resolved mandal_id to avoid ambiguity.
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geography import Booth, Mandal, Village, VillageAlias


async def resolve_mandal_id(db: AsyncSession, mandal_name: str) -> int:
    stmt = select(Mandal.id).where(func.lower(Mandal.name) == mandal_name.strip().lower())
    mandal_id = (await db.execute(stmt)).scalar_one_or_none()
    if mandal_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown mandal '{mandal_name}'")
    return mandal_id


async def resolve_village_id(db: AsyncSession, village_name: str, mandal_id: int) -> int:
    name = village_name.strip().lower()
    stmt = select(Village.id).where(func.lower(Village.name) == name, Village.mandal_id == mandal_id)
    village_id = (await db.execute(stmt)).scalar_one_or_none()
    if village_id is None:
        alias_stmt = select(VillageAlias.village_id).where(
            func.lower(VillageAlias.alias) == name, VillageAlias.mandal_id == mandal_id
        )
        village_id = (await db.execute(alias_stmt)).scalar_one_or_none()
    if village_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown village '{village_name}' in that mandal"
        )
    return village_id


async def resolve_booth_id(db: AsyncSession, booth_number: str | None, mandal_id: int) -> int | None:
    """Resolves a booth_number to its internal booth_id, scoped to a mandal_id.

    Same pattern as resolve_village_id: booth numbers are only unique within
    a mandal (schema.sql's UNIQUE constraint is (mandal_id, booth_number)).
    booth_id stays optional on voters, so a blank booth_number is a no-op —
    it's only an error if a booth_number was given but not found.
    """
    if not booth_number:
        return None
    stmt = select(Booth.id).where(
        Booth.booth_number == booth_number.strip(), Booth.mandal_id == mandal_id
    )
    booth_id = (await db.execute(stmt)).scalar_one_or_none()
    if booth_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown booth_number '{booth_number}' in that mandal"
        )
    return booth_id


async def load_geography_maps(
    db: AsyncSession,
) -> tuple[dict[str, int], dict[tuple[int, str], int], dict[tuple[int, str], int]]:
    """Loads every mandal/village/booth into memory once, for bulk-import lookups.

    A bulk sheet can carry thousands of rows, each needing a mandal/village/
    booth lookup — doing that via resolve_mandal_id/resolve_village_id/
    resolve_booth_id (one or more queries per row) would mean several
    sequential round trips per row. These tables are small (dozens to low
    hundreds of rows), so loading them all once and resolving every row from
    an in-memory dict is far cheaper. Used by the voters, development works,
    and beneficiary-scheme bulk-upload endpoints.
    """
    mandals = (await db.execute(select(Mandal.id, Mandal.name))).all()
    mandal_map = {m.name.strip().lower(): m.id for m in mandals}

    villages = (await db.execute(select(Village.id, Village.mandal_id, Village.name))).all()
    village_map = {(v.mandal_id, v.name.strip().lower()): v.id for v in villages}

    aliases = (await db.execute(select(VillageAlias.village_id, VillageAlias.mandal_id, VillageAlias.alias))).all()
    for a in aliases:
        # Canonical village names always win; an alias only fills in a key
        # that isn't already a real village name (there shouldn't be a
        # collision, but this keeps canonical resolution authoritative).
        village_map.setdefault((a.mandal_id, a.alias.strip().lower()), a.village_id)

    booths = (await db.execute(select(Booth.id, Booth.mandal_id, Booth.booth_number))).all()
    booth_map = {(b.mandal_id, b.booth_number.strip()): b.id for b in booths}

    return mandal_map, village_map, booth_map


async def resolve_geography(
    db: AsyncSession,
    *,
    mandal_name: str | None,
    village_name: str | None,
) -> tuple[int | None, int | None]:
    """Resolves an (optional) mandal_name + village_name pair to (mandal_id, village_id).

    A village_name without a mandal_name is rejected — village names aren't
    globally unique, so there's no safe way to resolve one alone.
    """
    if mandal_name is None:
        if village_name is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "village_name requires mandal_name"
            )
        return None, None

    mandal_id = await resolve_mandal_id(db, mandal_name)
    village_id = await resolve_village_id(db, village_name, mandal_id) if village_name else None
    return mandal_id, village_id
