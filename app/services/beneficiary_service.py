from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemes import Beneficiary


async def link_voter_by_epic(db: AsyncSession, epic_no: str | None) -> int | None:
    if not epic_no:
        return None
    from app.models.voters import Voter

    stmt = select(Voter.id).where(Voter.epic_no == epic_no.upper())
    voter_id = (await db.execute(stmt)).scalar_one_or_none()
    return voter_id


async def get_beneficiary_or_404(db: AsyncSession, beneficiary_id: int) -> Beneficiary:
    obj = await db.get(Beneficiary, beneficiary_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficiary not found")
    return obj
