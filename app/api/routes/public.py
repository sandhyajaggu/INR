from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import DbSession
from app.models.voters import Voter
from app.schemas.contact import PublicVoterLookupOut

router = APIRouter(prefix="/public", tags=["Public"])


@router.get(
    "/voter-lookup/{epic_no}",
    response_model=PublicVoterLookupOut,
    summary="Voter-ID autofill lookup (public, unauthenticated)",
    description="Used by the public Contact Us form to autofill Name/Mobile/Village/Mandal from an EPIC number. 404 if not found — frontend falls back to manual entry.",
)
async def public_voter_lookup(epic_no: str, db: DbSession) -> Voter:
    stmt = select(Voter).where(Voter.epic_no == epic_no.upper())
    voter = (await db.execute(stmt)).scalar_one_or_none()
    if voter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "EPIC number not found")
    return voter
