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

from app.models.geography import Mandal, Village


async def resolve_mandal_id(db: AsyncSession, mandal_name: str) -> int:
    stmt = select(Mandal.id).where(func.lower(Mandal.name) == mandal_name.strip().lower())
    mandal_id = (await db.execute(stmt)).scalar_one_or_none()
    if mandal_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown mandal '{mandal_name}'")
    return mandal_id


async def resolve_village_id(db: AsyncSession, village_name: str, mandal_id: int) -> int:
    stmt = select(Village.id).where(
        func.lower(Village.name) == village_name.strip().lower(), Village.mandal_id == mandal_id
    )
    village_id = (await db.execute(stmt)).scalar_one_or_none()
    if village_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Unknown village '{village_name}' in that mandal"
        )
    return village_id


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
