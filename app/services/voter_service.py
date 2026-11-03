from datetime import datetime, timezone
from math import ceil
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import UserScope
from app.models.geography import Booth, Mandal, Village
from app.models.voters import Voter
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError
from app.schemas.voters import VoterBulkRow, VoterFields
from app.services.activity_service import log_activity
from app.services.encryption_service import encrypt_aadhaar
from app.services.geography_service import load_geography_maps, resolve_geography
from app.services.voter_profile import gender_to_db, removed_row, strip_booth_label, voter_rows

# Voters-page sort keys -> SQL expressions.
SORT_COLUMNS = {
    "epic_no": Voter.epic_no,
    "name": Voter.name,
    "relation_type": Voter.relation_type,
    "relation_name": Voter.relation_name,
    "gender": Voter.gender,
    "age": Voter.age,
    "religion": Voter.religion,
    "caste_category": Voter.caste_category,
    "mandal": Mandal.name,
    "village": Village.name,
    "booth_no": Booth.booth_number,
    "mobile": Voter.mobile,
    "alt_mobile": Voter.alt_mobile,
    "voted_last_election": Voter.voted_last_election,
    "is_new_voter": Voter.is_new_voter,
    "status": Voter.status,
    "dob": Voter.dob,
    "id": Voter.id,
}

# Voters-page card filters (activeFilterKey).
CARD_FILTERS = {
    "male": Voter.gender == "Male",
    "female": Voter.gender == "Female",
    "third": Voter.gender == "Other",
    "new": Voter.is_new_voter.is_(True),
}


def _active():
    return Voter.removed_at.is_(None)


async def search_voters(
    db: AsyncSession,
    *,
    scope: UserScope,
    page: int,
    page_size: int,
    q: str | None = None,
    filter_key: str | None = None,
    gender: str | None = None,
    epic_no: str | None = None,
    name: str | None = None,
    mandal: str | None = None,
    village: str | None = None,
    booth_no: str | None = None,
    mandal_id: int | None = None,
    village_id: int | None = None,
    booth_id: int | None = None,
    status_filter: str | None = None,
    sort_key: str | None = None,
    sort_dir: str = "asc",
) -> dict[str, Any]:
    base = (
        select(Voter.id)
        .join(Mandal, Mandal.id == Voter.mandal_id)
        .join(Village, Village.id == Voter.village_id)
        .outerjoin(Booth, Booth.id == Voter.booth_id)
        .where(_active())
    )
    base = scope.apply(base, mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)

    if filter_key in CARD_FILTERS:
        base = base.where(CARD_FILTERS[filter_key])
    if gender:
        base = base.where(Voter.gender == gender_to_db(gender))
    if epic_no:
        base = base.where(Voter.epic_no == epic_no.strip().upper())
    if name:
        base = base.where(Voter.name.ilike(f"%{name.strip()}%"))
    if mandal:
        base = base.where(func.lower(Mandal.name) == mandal.strip().lower())
    if village:
        base = base.where(func.lower(Village.name) == village.strip().lower())
    if booth_no:
        base = base.where(Booth.booth_number == strip_booth_label(booth_no))
    if mandal_id is not None:
        base = base.where(Voter.mandal_id == mandal_id)
    if village_id is not None:
        base = base.where(Voter.village_id == village_id)
    if booth_id is not None:
        base = base.where(Voter.booth_id == booth_id)
    if status_filter:
        base = base.where(Voter.status == status_filter)
    if q and q.strip():
        term = f"%{q.strip()}%"
        base = base.where(
            or_(
                Voter.epic_no.ilike(term),
                Voter.name.ilike(term),
                Voter.relation_name.ilike(term),
                Voter.mobile.ilike(term),
                Mandal.name.ilike(term),
                Village.name.ilike(term),
                Booth.booth_number.ilike(term.replace("#", "")),
            )
        )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    sort_col = SORT_COLUMNS.get(sort_key or "")
    if sort_col is not None:
        order = sort_col.desc().nulls_last() if sort_dir == "desc" else sort_col.asc().nulls_last()
        base = base.order_by(order, Voter.id.desc())
    elif name and not q:
        base = base.order_by(func.similarity(Voter.name, name).desc())
    else:
        base = base.order_by(Voter.id.desc())

    page_ids = list((await db.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().all())
    voters = (await db.execute(select(Voter).where(Voter.id.in_(page_ids or [-1])))).scalars().all()
    by_id = {v.id: v for v in voters}
    ordered = [by_id[i] for i in page_ids if i in by_id]

    return {
        "items": await voter_rows(db, ordered),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if page_size else 0,
    }


async def voter_stats(db: AsyncSession, scope: UserScope) -> dict[str, int]:
    """The five cards on the Voters page (Total, Male, Female, Third gender, New) + Removed."""
    stmt = select(
        func.count().filter(_active()),
        func.count().filter(_active(), Voter.gender == "Male"),
        func.count().filter(_active(), Voter.gender == "Female"),
        func.count().filter(_active(), Voter.gender == "Other"),
        func.count().filter(_active(), Voter.is_new_voter.is_(True)),
        func.count().filter(Voter.removed_at.is_not(None)),
    ).select_from(Voter)
    stmt = scope.apply(stmt, mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)
    total, male, female, third, new, removed = (await db.execute(stmt)).one()
    return {
        "total": total,
        "male": male,
        "female": female,
        "thirdGender": third,
        "newVoters": new,
        "removed": removed,
    }


async def list_removed_voters(db: AsyncSession, scope: UserScope, limit: int) -> list[dict[str, Any]]:
    stmt = (
        select(Voter, Village.name, Booth.booth_number)
        .join(Village, Village.id == Voter.village_id)
        .outerjoin(Booth, Booth.id == Voter.booth_id)
        .where(Voter.removed_at.is_not(None))
    )
    stmt = scope.apply(stmt, mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)
    rows = (await db.execute(stmt.order_by(Voter.removed_at.desc()).limit(limit))).all()
    return [removed_row(v, village, booth) for v, village, booth in rows]


async def get_voter_or_404(db: AsyncSession, voter_id: str | int, *, include_removed: bool = True) -> Voter:
    """Resolves a voter by internal numeric id or by EPIC number."""
    key = str(voter_id).strip()
    if key.isdigit():
        voter = await db.get(Voter, int(key))
    else:
        stmt = select(Voter).where(Voter.epic_no == key.upper())
        voter = (await db.execute(stmt)).scalar_one_or_none()
    if voter is None or (not include_removed and voter.removed_at is not None):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voter not found")
    return voter


async def voter_values(db: AsyncSession, payload: VoterFields) -> dict[str, Any]:
    """Column values for a voter from the Add/Edit form (mandal/village/booth resolved to ids)."""
    data = payload.model_dump()
    mandal_id, village_id = await resolve_geography(db, mandal_name=data.pop("mandal"), village_name=data.pop("village"))
    booth_no = data.pop("booth_no")
    booth_id = data.pop("booth_id")
    if booth_no:
        stmt = select(Booth.id).where(Booth.mandal_id == mandal_id, Booth.booth_number == booth_no)
        booth_id = (await db.execute(stmt)).scalar_one_or_none()
        if booth_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Booth #{booth_no} does not exist in this mandal. Add it on the Booths page first.",
            )
    if data.get("aadhaar_number"):
        data["aadhaar_number"] = encrypt_aadhaar(data["aadhaar_number"])
    else:
        data.pop("aadhaar_number", None)
    if data.get("mobile_verified") is None:
        data.pop("mobile_verified", None)
    data.update(mandal_id=mandal_id, village_id=village_id, booth_id=booth_id)
    return data


async def remove_voter(db: AsyncSession, voter: Voter, *, reason: str, details: str | None, actor) -> None:
    if voter.removed_at is not None:
        return
    voter.removed_at = datetime.now(timezone.utc)
    voter.removal_reason = reason
    voter.removal_details = details
    voter.removed_by = actor.name
    await log_activity(
        db,
        actor_id=actor.id,
        action_type="voter_removed",
        module="voters",
        reference_id=voter.id,
        description=f"Removed voter {voter.epic_no} ({reason})",
        changes=[["status", "Active", f"Removed ({reason})"]],
    )


async def restore_voter(db: AsyncSession, voter: Voter, *, actor) -> None:
    if voter.removed_at is None:
        return
    reason = voter.removal_reason
    voter.removed_at = None
    voter.removal_reason = None
    voter.removal_details = None
    voter.removed_by = None
    await log_activity(
        db,
        actor_id=actor.id,
        action_type="voter_restored",
        module="voters",
        reference_id=voter.id,
        description=f"Restored voter {voter.epic_no}",
        changes=[["status", f"Removed ({reason})", "Active"]],
    )


def set_polling_mark(voter: Voter, *, voted: bool, party: str | None, marked_by: str) -> None:
    """Polling Day: mark/unmark a voter as voted. Also keeps voted_last_election in step (as the dashboard does)."""
    if voted:
        voter.polling_status = "voted"
        voter.voted_party = party or None
        voter.marked_at = datetime.now(timezone.utc)
        voter.marked_by = marked_by
        voter.voted_last_election = True
    else:
        voter.polling_status = "not_voted"
        voter.voted_party = None
        voter.marked_at = None
        voter.marked_by = None
        voter.voted_last_election = False


async def bulk_import_voters(db: AsyncSession, rows: list[dict], actor_id: int) -> BulkImportResult:
    """All-or-nothing bulk import of voters from an uploaded sheet.

    Every row is validated in full before anything is written: field format,
    duplicate epic_no within the file, and resolvable mandal/village/booth.
    If any row has any problem, nothing is written and the complete list of
    row errors is returned so the whole sheet can be corrected in one pass.
    A row whose epic_no already exists updates that voter (the sheet is
    authoritative for every field it carries) instead of being rejected.
    """
    errors: list[BulkImportRowError] = []
    parsed_rows: list[tuple[int, VoterBulkRow]] = []

    for raw in rows:
        row_num = raw.get("_row_number")
        epic_hint = str(raw.get("epic_no") or "").strip().upper() or None
        try:
            parsed_rows.append((row_num, VoterBulkRow.model_validate(raw)))
        except ValidationError as exc:
            reason = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
            errors.append(BulkImportRowError(row=row_num, epic_no=epic_hint, reason=reason))

    first_seen: dict[str, int] = {}
    for row_num, parsed in parsed_rows:
        if parsed.epic_no in first_seen:
            errors.append(
                BulkImportRowError(
                    row=row_num,
                    epic_no=parsed.epic_no,
                    reason=f"Duplicate epic_no within file (first seen on row {first_seen[parsed.epic_no]})",
                )
            )
        else:
            first_seen[parsed.epic_no] = row_num

    existing_voters: dict[str, Voter] = {}
    if first_seen:
        # asyncpg caps a statement at 32767 bind parameters; batch the IN().
        epic_keys = list(first_seen.keys())
        for i in range(0, len(epic_keys), 5000):
            batch = epic_keys[i : i + 5000]
            for voter in (await db.execute(select(Voter).where(Voter.epic_no.in_(batch)))).scalars().all():
                existing_voters[voter.epic_no] = voter

    mandal_map, village_map, booth_map = await load_geography_maps(db)
    resolved: list[tuple[VoterBulkRow, int, int, int | None]] = []
    for row_num, parsed in parsed_rows:
        mandal_id = mandal_map.get(parsed.mandal.strip().lower())
        if mandal_id is None:
            errors.append(
                BulkImportRowError(row=row_num, epic_no=parsed.epic_no, reason=f"Unknown mandal '{parsed.mandal}'")
            )
            continue
        village_id = village_map.get((mandal_id, parsed.village.strip().lower()))
        if village_id is None:
            errors.append(
                BulkImportRowError(
                    row=row_num,
                    epic_no=parsed.epic_no,
                    reason=f"Unknown village '{parsed.village}' in mandal '{parsed.mandal}'",
                )
            )
            continue
        booth_id = None
        if parsed.booth_no:
            booth_id = booth_map.get((mandal_id, parsed.booth_no.strip()))
            if booth_id is None:
                errors.append(
                    BulkImportRowError(
                        row=row_num,
                        epic_no=parsed.epic_no,
                        reason=f"Unknown booth '{parsed.booth_no}' in mandal '{parsed.mandal}'",
                    )
                )
                continue
        resolved.append((parsed, mandal_id, village_id, booth_id))

    if errors:
        return BulkImportResult(inserted=0, errors=errors)

    new_voters = []
    updated_count = 0
    for parsed, mandal_id, village_id, booth_id in resolved:
        # Only the columns present in the sheet overwrite an existing voter.
        data = parsed.model_dump(exclude={"mandal", "village", "booth_no", "booth_id"}, exclude_unset=True)
        if data.get("aadhaar_number"):
            data["aadhaar_number"] = encrypt_aadhaar(data["aadhaar_number"])
        existing = existing_voters.get(parsed.epic_no)
        if existing is not None:
            for field, value in data.items():
                setattr(existing, field, value)
            existing.mandal_id = mandal_id
            existing.village_id = village_id
            existing.booth_id = booth_id
            updated_count += 1
        else:
            full = parsed.model_dump(exclude={"mandal", "village", "booth_no", "booth_id"})
            if full.get("aadhaar_number"):
                full["aadhaar_number"] = encrypt_aadhaar(full["aadhaar_number"])
            if full.get("mobile_verified") is None:
                full.pop("mobile_verified")
            new_voters.append(Voter(**full, mandal_id=mandal_id, village_id=village_id, booth_id=booth_id))

    db.add_all(new_voters)
    await db.flush()
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="voter_bulk_imported",
        module="voters",
        reference_id=None,
        description=f"Bulk import: {len(new_voters)} voters added, {updated_count} updated",
    )
    await db.commit()
    return BulkImportResult(inserted=len(new_voters), updated=updated_count, errors=[])


__all__ = [
    "bulk_import_voters",
    "get_voter_or_404",
    "list_removed_voters",
    "remove_voter",
    "restore_voter",
    "search_voters",
    "set_polling_mark",
    "voter_rows",
    "voter_stats",
    "voter_values",
]
