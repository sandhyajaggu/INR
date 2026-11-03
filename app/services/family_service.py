"""Families page helpers (frontend: Families.jsx, FamilyDetailsDrawer, MapFamilyModal, ...)."""

from math import ceil
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.ids import format_id, parse_id
from app.core.scope import UserScope
from app.models.families import Family, FamilyMember
from app.models.geography import Booth, Mandal, Village
from app.models.schemes import Beneficiary
from app.models.voters import Voter
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError
from app.schemas.families import FamilyBulkRow
from app.services.activity_service import log_activity
from app.services.geography_service import resolve_geography
from app.services.voter_profile import booth_label, strip_booth_label, survey_summaries

FAMILY_PREFIX = "FAM"
HEAD_RELATION = "Self (Head)"


async def get_family_or_404(db: AsyncSession, family_id: str) -> Family:
    stmt = (
        select(Family)
        .where(Family.id == parse_id(family_id, label="Family"))
        .options(selectinload(Family.members))
    )
    family = (await db.execute(stmt)).scalar_one_or_none()
    if family is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Family not found")
    return family


async def find_voter(db: AsyncSession, ref: dict[str, Any]) -> Voter:
    """The voter a request refers to: by epic / epic_no, or by numeric id."""
    epic = ref.get("epic") or ref.get("epic_no") or ref.get("head_epic")
    if epic:
        stmt = select(Voter).where(Voter.epic_no == str(epic).strip().upper())
        voter = (await db.execute(stmt)).scalar_one_or_none()
    elif ref.get("id") is not None and str(ref["id"]).isdigit():
        voter = await db.get(Voter, int(ref["id"]))
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the voter's epic (EPIC number)")
    if voter is None or voter.removed_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Voter {epic or ref.get('id')} not found")
    return voter


async def _ensure_unmapped(db: AsyncSession, voter: Voter) -> None:
    existing = (
        await db.execute(select(FamilyMember.family_id).where(FamilyMember.voter_id == voter.id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Voter {voter.epic_no} is already in family {format_id(FAMILY_PREFIX, existing)}",
        )


async def _schemes_count(db: AsyncSession, epics: list[str]) -> int:
    if not epics:
        return 0
    stmt = select(func.count()).select_from(Beneficiary).where(Beneficiary.epic_no.in_(epics))
    return (await db.execute(stmt)).scalar_one()


async def create_family(db: AsyncSession, head: Voter, *, actor_id: int, mobile: str | None = None) -> Family:
    await _ensure_unmapped(db, head)
    booth_number = None
    if head.booth_id:
        booth_number = (await db.execute(select(Booth.booth_number).where(Booth.id == head.booth_id))).scalar_one_or_none()
    family = Family(
        head_voter_id=head.id,
        head_name=head.name,
        mobile=mobile or head.mobile,
        mandal_id=head.mandal_id,
        village_id=head.village_id,
        booth_no=booth_number,
        members_count=1,
        schemes_availed=await _schemes_count(db, [head.epic_no]),
    )
    family.members = [FamilyMember(voter_id=head.id, relation=HEAD_RELATION)]
    db.add(family)
    await db.flush()
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="family_added",
        module="families",
        reference_id=family.id,
        description=f"Created family {format_id(FAMILY_PREFIX, family.id)} headed by {head.name} ({head.epic_no})",
    )
    return family


async def add_member(db: AsyncSession, family: Family, voter: Voter, relation: str, *, actor_id: int) -> None:
    await _ensure_unmapped(db, voter)
    family.members.append(FamilyMember(voter_id=voter.id, relation=relation or "Member"))
    await db.flush()
    family.members_count = len(family.members)
    member_epics = (
        await db.execute(
            select(Voter.epic_no).where(Voter.id.in_([m.voter_id for m in family.members]))
        )
    ).scalars().all()
    family.schemes_availed = await _schemes_count(db, list(member_epics))
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="family_member_added",
        module="families",
        reference_id=family.id,
        description=f"Added {voter.name} ({voter.epic_no}) to family {format_id(FAMILY_PREFIX, family.id)} as {relation}",
    )


async def remove_member(db: AsyncSession, family: Family, voter: Voter, *, actor_id: int) -> None:
    if voter.id == family.head_voter_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The head of the family can't be removed; delete the family instead")
    member = next((m for m in family.members if m.voter_id == voter.id), None)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voter is not a member of this family")
    family.members.remove(member)
    await db.flush()
    family.members_count = len(family.members)
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="family_member_removed",
        module="families",
        reference_id=family.id,
        description=f"Removed {voter.epic_no} from family {format_id(FAMILY_PREFIX, family.id)}",
    )


async def apply_family_update(db: AsyncSession, family: Family, data: dict[str, Any]) -> None:
    """Edit Family form / drawer: any subset of head_name, members_count, schemes_availed,
    mobile, mandal, village, booth_no, children_under_18."""
    if "mandal" in data or "village" in data:
        mandal_name = data.pop("mandal", None)
        village_name = data.pop("village", None)
        if mandal_name:
            family.mandal_id, family.village_id = await resolve_geography(
                db, mandal_name=mandal_name, village_name=village_name
            )
    if "booth_no" in data:
        data["booth_no"] = strip_booth_label(data["booth_no"])
    for field, value in data.items():
        setattr(family, field, value)


async def family_rows(db: AsyncSession, families: list[Family]) -> list[dict[str, Any]]:
    if not families:
        return []
    voter_ids = {m.voter_id for f in families for m in f.members} | {f.head_voter_id for f in families}
    voters = {
        v.id: v for v in (await db.execute(select(Voter).where(Voter.id.in_(voter_ids)))).scalars().all()
    }
    booth_ids = {v.booth_id for v in voters.values() if v.booth_id}
    booths = {}
    if booth_ids:
        booths = dict((await db.execute(select(Booth.id, Booth.booth_number).where(Booth.id.in_(booth_ids)))).all())
    geo_ids = {f.mandal_id for f in families if f.mandal_id}
    mandals = dict((await db.execute(select(Mandal.id, Mandal.name).where(Mandal.id.in_(geo_ids or {-1})))).all())
    village_ids = {f.village_id for f in families if f.village_id}
    villages = dict((await db.execute(select(Village.id, Village.name).where(Village.id.in_(village_ids or {-1})))).all())
    surveys = await survey_summaries(db, list(voter_ids))

    out = []
    for f in families:
        head = voters.get(f.head_voter_id)
        members = []
        for m in f.members:
            v = voters.get(m.voter_id)
            if v is None:
                continue
            members.append(
                {
                    "epic": v.epic_no,
                    "name": v.name,
                    "relation": m.relation,
                    "booth": booth_label(booths.get(v.booth_id)),
                    "mobile": v.mobile,
                    "survey": "Completed" if surveys.get(v.id, {}).get("survey_done") else "Pending",
                    "head": v.id == f.head_voter_id,
                    "voter_id": v.id,
                }
            )
        out.append(
            {
                "id": format_id(FAMILY_PREFIX, f.id),
                "head_name": f.head_name,
                "head_epic": head.epic_no if head else None,
                "head_photo": head.photo_url if head else None,
                "members_count": f.members_count,
                "mandal": mandals.get(f.mandal_id),
                "village": villages.get(f.village_id),
                "booth_no": f.booth_no,
                "schemes_availed": f.schemes_availed,
                "mobile": f.mobile,
                "children_under_18": f.children_under_18,
                "members": members,
                "createdAt": f.created_at,
                "updatedAt": f.updated_at,
            }
        )
    return out


async def list_families(
    db: AsyncSession,
    *,
    scope: UserScope,
    page: int,
    page_size: int,
    q: str | None,
    mandal: str | None,
    sort_key: str | None,
    sort_dir: str,
) -> dict[str, Any]:
    stmt = (
        select(Family.id)
        .outerjoin(Mandal, Mandal.id == Family.mandal_id)
        .outerjoin(Village, Village.id == Family.village_id)
        .join(Voter, Voter.id == Family.head_voter_id)
    )
    stmt = scope.apply(stmt, mandal_col=Family.mandal_id)
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if q and q.strip():
        term = f"%{q.strip()}%"
        conditions = [
            Family.head_name.ilike(term),
            Voter.epic_no.ilike(term),
            Mandal.name.ilike(term),
            Village.name.ilike(term),
            Family.mobile.ilike(term),
        ]
        digits = "".join(ch for ch in q if ch.isdigit())
        if q.strip().upper().startswith("FAM") and digits:
            conditions.append(Family.id == int(digits))
        stmt = stmt.where(or_(*conditions))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    sort_cols = {
        "id": Family.id,
        "head_name": Family.head_name,
        "members_count": Family.members_count,
        "mandal": Mandal.name,
        "village": Village.name,
        "booth_no": Family.booth_no,
        "schemes_availed": Family.schemes_availed,
        "mobile": Family.mobile,
    }
    col = sort_cols.get(sort_key or "")
    if col is not None:
        stmt = stmt.order_by(col.desc() if sort_dir == "desc" else col.asc(), Family.id.desc())
    else:
        stmt = stmt.order_by(Family.id.desc())
    ids = list((await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all())
    families = (
        await db.execute(select(Family).where(Family.id.in_(ids or [-1])).options(selectinload(Family.members)))
    ).scalars().all()
    by_id = {f.id: f for f in families}
    return {
        "items": await family_rows(db, [by_id[i] for i in ids if i in by_id]),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if page_size else 0,
    }


def _unmapped_query(scope: UserScope):
    mapped = select(FamilyMember.voter_id)
    stmt = (
        select(Voter, Mandal.name, Village.name, Booth.booth_number)
        .join(Mandal, Mandal.id == Voter.mandal_id)
        .join(Village, Village.id == Voter.village_id)
        .outerjoin(Booth, Booth.id == Voter.booth_id)
        .where(Voter.removed_at.is_(None), Voter.id.not_in(mapped))
    )
    return scope.apply(stmt, mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)


async def list_unmapped_voters(
    db: AsyncSession,
    *,
    scope: UserScope,
    page: int,
    page_size: int,
    q: str | None,
    mandal: str | None,
    village: str | None,
    booth_no: str | None,
) -> dict[str, Any]:
    stmt = _unmapped_query(scope)
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if village:
        stmt = stmt.where(func.lower(Village.name) == village.strip().lower())
    if booth_no:
        stmt = stmt.where(Booth.booth_number == strip_booth_label(booth_no))
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Voter.name.ilike(term), Voter.epic_no.ilike(term), Voter.relation_name.ilike(term)))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(stmt.order_by(Village.name, Voter.relation_name, Voter.id).offset((page - 1) * page_size).limit(page_size))
    ).all()
    items = [
        {
            "id": v.id,
            "epic": v.epic_no,
            "name": v.name,
            "relation": " ".join(x for x in (v.relation_type or "", v.relation_name or "") if x).strip() or None,
            "age": v.age,
            "booth": booth_label(booth),
            "mandal": mandal_name,
            "village": village_name,
            "mobile": v.mobile,
        }
        for v, mandal_name, village_name, booth in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if page_size else 0,
    }


async def family_stats(db: AsyncSession, scope: UserScope) -> dict[str, Any]:
    fam_stmt = scope.apply(select(func.count()).select_from(Family), mandal_col=Family.mandal_id)
    total_families = (await db.execute(fam_stmt)).scalar_one()
    mapped_stmt = (
        select(func.count(), func.count(func.distinct(Voter.booth_id)))
        .select_from(FamilyMember)
        .join(Voter, Voter.id == FamilyMember.voter_id)
        .where(Voter.removed_at.is_(None))
    )
    mapped_stmt = scope.apply(mapped_stmt, mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)
    mapped, across_booths = (await db.execute(mapped_stmt)).one()
    voters_stmt = scope.apply(
        select(func.count()).select_from(Voter).where(Voter.removed_at.is_(None)),
        mandal_col=Voter.mandal_id,
        booth_col=Voter.booth_id,
    )
    total_voters = (await db.execute(voters_stmt)).scalar_one()
    unmapped = max(total_voters - mapped, 0)
    return {
        "totalFamilies": total_families,
        "mappedVotersCount": mapped,
        "unmappedCount": unmapped,
        "mappedPct": round(mapped * 100 / total_voters) if total_voters else 0,
        "acrossBooths": across_booths,
    }


async def bulk_import_families(db: AsyncSession, rows: list[dict], actor_id: int) -> BulkImportResult:
    """All-or-nothing: each row creates a family headed by the voter with Head EPIC."""
    errors: list[BulkImportRowError] = []
    parsed: list[tuple[int, FamilyBulkRow]] = []
    for raw in rows:
        row_num = raw.get("_row_number")
        try:
            parsed.append((row_num, FamilyBulkRow.model_validate(raw)))
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
            errors.append(BulkImportRowError(row=row_num, epic_no=str(raw.get("head_epic") or "") or None, reason=reason))

    epics = [p.head_epic for _, p in parsed]
    voters = {
        v.epic_no: v
        for v in (await db.execute(select(Voter).where(Voter.epic_no.in_(epics or ["-"])))).scalars().all()
    }
    already = set(
        (
            await db.execute(
                select(Voter.epic_no).join(FamilyMember, FamilyMember.voter_id == Voter.id).where(Voter.epic_no.in_(epics or ["-"]))
            )
        ).scalars().all()
    )
    seen: dict[str, int] = {}
    for row_num, p in parsed:
        voter = voters.get(p.head_epic)
        if voter is None or voter.removed_at is not None:
            errors.append(BulkImportRowError(row=row_num, epic_no=p.head_epic, reason="Head EPIC not found in voters"))
        elif p.head_epic in already:
            errors.append(BulkImportRowError(row=row_num, epic_no=p.head_epic, reason="Voter is already in a family"))
        elif p.head_epic in seen:
            errors.append(
                BulkImportRowError(row=row_num, epic_no=p.head_epic, reason=f"Duplicate Head EPIC (first on row {seen[p.head_epic]})")
            )
        else:
            seen[p.head_epic] = row_num
    if errors:
        errors.sort(key=lambda e: e.row)
        return BulkImportResult(inserted=0, errors=errors)

    for _, p in parsed:
        family = await create_family(db, voters[p.head_epic], actor_id=actor_id, mobile=p.mobile)
        if p.booth_no:
            family.booth_no = p.booth_no
    await db.commit()
    return BulkImportResult(inserted=len(parsed), errors=[])
