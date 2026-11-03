"""Geographic scope of a signed-in user (the "Scope" field in User Management).

    "All mandals"             -> everything
    "<Name> Mandal"           -> that mandal only
    "Assigned mandal only"    -> the user's own mandal
    "Assigned booth only"     -> booths whose agent mobile is the user's mobile

The frontend filters lists by scope too; doing it here keeps API data
consistent with what the user is allowed to see.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geography import Booth, Mandal
from app.models.staff import StaffUser


@dataclass
class UserScope:
    mandal_id: int | None = None
    booth_ids: list[int] | None = None
    restricted: bool = False

    def apply(self, stmt, *, mandal_col=None, booth_col=None):
        """Add scope conditions to a select. Pass whichever columns the table has."""
        if not self.restricted:
            return stmt
        if self.booth_ids is not None and booth_col is not None:
            return stmt.where(booth_col.in_(self.booth_ids or [-1]))
        if self.mandal_id is not None and mandal_col is not None:
            return stmt.where(mandal_col == self.mandal_id)
        if self.mandal_id is None and self.booth_ids is None:
            # Restricted scope that couldn't be resolved -> nothing visible.
            col = mandal_col if mandal_col is not None else booth_col
            if col is not None:
                return stmt.where(col == -1)
        return stmt


async def _mandal_id_by_name(db: AsyncSession, name: str | None) -> int | None:
    if not name:
        return None
    stmt = select(Mandal.id).where(func.lower(Mandal.name) == name.strip().lower())
    return (await db.execute(stmt)).scalar_one_or_none()


async def resolve_scope(db: AsyncSession, user: StaffUser) -> UserScope:
    if user.role == "super_admin":
        return UserScope()
    scope = (user.scope or "All mandals").strip()
    if scope == "All mandals":
        return UserScope()
    if scope == "Assigned booth only":
        booth_ids: list[int] = []
        if user.mobile:
            stmt = select(Booth.id).where(Booth.booth_officer_mobile == user.mobile)
            booth_ids = list((await db.execute(stmt)).scalars().all())
        return UserScope(
            mandal_id=await _mandal_id_by_name(db, user.mandal), booth_ids=booth_ids, restricted=True
        )
    if scope == "Assigned mandal only":
        return UserScope(mandal_id=await _mandal_id_by_name(db, user.mandal), restricted=True)
    if scope.endswith(" Mandal"):
        return UserScope(mandal_id=await _mandal_id_by_name(db, scope[: -len(" Mandal")]), restricted=True)
    return UserScope()
