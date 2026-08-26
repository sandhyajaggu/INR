from math import ceil

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voters import Voter
from app.schemas.common import PaginatedResponse
from app.schemas.voters import VoterOut


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
