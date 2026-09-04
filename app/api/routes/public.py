from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import DbSession
from app.models.geography import Mandal, Village
from app.models.voters import Voter
from app.schemas.contact import PublicVoterLookupOut

router = APIRouter(prefix="/public", tags=["Public"])


@router.get(
    "/voter-lookup/{epic_no}",
    response_model=PublicVoterLookupOut,
    summary="Voter-ID autofill lookup (public, unauthenticated)",
    description="Used by the public Contact Us form to autofill Name/Mobile/Village/Mandal from an EPIC number. 404 if not found — frontend falls back to manual entry.",
)
async def public_voter_lookup(epic_no: str, db: DbSession) -> PublicVoterLookupOut:
    stmt = (
        select(Voter, Village.name, Mandal.name)
        .join(Village, Village.id == Voter.village_id)
        .join(Mandal, Mandal.id == Voter.mandal_id)
        .where(Voter.epic_no == epic_no.upper())
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "EPIC number not found")
    voter, village_name, mandal_name = row
    return PublicVoterLookupOut(
        name=voter.name,
        mobile=voter.mobile,
        village_id=voter.village_id,
        village_name=village_name,
        mandal_id=voter.mandal_id,
        mandal_name=mandal_name,
    )
