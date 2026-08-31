from math import ceil

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voters import Voter
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError
from app.schemas.common import PaginatedResponse
from app.schemas.voters import VoterBulkRow, VoterOut
from app.services.activity_service import log_activity
from app.services.encryption_service import encrypt_aadhaar
from app.services.geography_service import load_geography_maps


def to_voter_out(voter: Voter) -> VoterOut:
    from app.services.encryption_service import mask_aadhaar

    return VoterOut(
        id=voter.id,
        epic_no=voter.epic_no,
        name=voter.name,
        relation_name=voter.relation_name,
        age=voter.age,
        gender=voter.gender,
        mobile=voter.mobile,
        aadhaar_masked=mask_aadhaar(voter.aadhaar_number),
        house_no=voter.house_no,
        village_id=voter.village_id,
        mandal_id=voter.mandal_id,
        booth_id=voter.booth_id,
        voted_last_election=voter.voted_last_election,
        is_new_voter=voter.is_new_voter,
        photo_url=voter.photo_url,
        created_at=voter.created_at,
        updated_at=voter.updated_at,
    )


async def search_voters(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    epic_no: str | None,
    name: str | None,
    mandal_id: int | None,
    village_id: int | None,
    booth_id: int | None,
    gender: str | None,
) -> PaginatedResponse[VoterOut]:
    stmt = select(Voter)
    count_stmt = select(func.count()).select_from(Voter)
    conditions = []

    if epic_no:
        conditions.append(Voter.epic_no == epic_no.upper())
    if name:
        # pg_trgm-backed fuzzy search: similarity ranking falls back to ILIKE
        # ordering on drivers/tests without the extension loaded.
        conditions.append(Voter.name.ilike(f"%{name}%"))
    if mandal_id is not None:
        conditions.append(Voter.mandal_id == mandal_id)
    if village_id is not None:
        conditions.append(Voter.village_id == village_id)
    if booth_id is not None:
        conditions.append(Voter.booth_id == booth_id)
    if gender:
        conditions.append(Voter.gender == gender)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    if name:
        stmt = stmt.order_by(func.similarity(Voter.name, name).desc())
    else:
        stmt = stmt.order_by(Voter.id.desc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    voters = (await db.execute(stmt)).scalars().all()

    return PaginatedResponse(
        items=[to_voter_out(v) for v in voters],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if page_size else 0,
    )


async def get_voter_or_404(db: AsyncSession, voter_id: int) -> Voter:
    voter = await db.get(Voter, voter_id)
    if voter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voter not found")
    return voter


async def bulk_import_voters(db: AsyncSession, rows: list[dict], actor_id: int) -> BulkImportResult:
    """All-or-nothing bulk import of voters from a parsed Excel sheet.

    Every row is validated in full before anything is written: field format,
    duplicate epic_no within the file, duplicate epic_no already in the
    database, and resolvable mandal_name/village_name/booth_number. If any
    row has any problem, nothing is inserted and the complete list of row
    errors is returned so the whole sheet can be corrected in one pass.
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

    if first_seen:
        # A large sheet can carry tens of thousands of epic_nos. SQLAlchemy's
        # .in_() binds one query parameter per value, and PostgreSQL/asyncpg
        # hard-caps a statement at 32767 bind parameters — a single query
        # over the full key set can exceed that and crash the request.
        # Batching keeps every query well under the limit.
        epic_keys = list(first_seen.keys())
        existing_epics: list[str] = []
        batch_size = 5000
        for i in range(0, len(epic_keys), batch_size):
            batch = epic_keys[i : i + batch_size]
            existing_epics.extend(
                (await db.execute(select(Voter.epic_no).where(Voter.epic_no.in_(batch)))).scalars().all()
            )
        for epic in existing_epics:
            errors.append(
                BulkImportRowError(row=first_seen[epic], epic_no=epic, reason="epic_no already exists in the database")
            )

    mandal_map, village_map, booth_map = await load_geography_maps(db)
    resolved: list[tuple[VoterBulkRow, int, int, int | None]] = []
    for row_num, parsed in parsed_rows:
        mandal_id = mandal_map.get(parsed.mandal_name.strip().lower())
        if mandal_id is None:
            errors.append(
                BulkImportRowError(row=row_num, epic_no=parsed.epic_no, reason=f"Unknown mandal_name '{parsed.mandal_name}'")
            )
            continue
        village_id = village_map.get((mandal_id, parsed.village_name.strip().lower()))
        if village_id is None:
            errors.append(
                BulkImportRowError(
                    row=row_num,
                    epic_no=parsed.epic_no,
                    reason=f"Unknown village_name '{parsed.village_name}' in mandal '{parsed.mandal_name}'",
                )
            )
            continue
        booth_id = None
        if parsed.booth_number:
            booth_id = booth_map.get((mandal_id, parsed.booth_number.strip()))
            if booth_id is None:
                errors.append(
                    BulkImportRowError(
                        row=row_num,
                        epic_no=parsed.epic_no,
                        reason=f"Unknown booth_number '{parsed.booth_number}' in mandal '{parsed.mandal_name}'",
                    )
                )
                continue
        resolved.append((parsed, mandal_id, village_id, booth_id))

    if errors:
        return BulkImportResult(inserted=0, errors=errors)

    voters = []
    for parsed, mandal_id, village_id, booth_id in resolved:
        data = parsed.model_dump(exclude={"mandal_name", "village_name", "booth_number"})
        if data.get("aadhaar_number"):
            data["aadhaar_number"] = encrypt_aadhaar(data["aadhaar_number"])
        voters.append(Voter(**data, mandal_id=mandal_id, village_id=village_id, booth_id=booth_id))

    db.add_all(voters)
    await db.flush()
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="voter_bulk_imported",
        module="voters",
        reference_id=None,
        description=f"Bulk import: {len(voters)} voters added",
    )
    await db.commit()
    return BulkImportResult(inserted=len(voters), errors=[])
