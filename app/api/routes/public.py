from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
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


# --- Public website pages ------------------------------------------------------
# The public site (PublicEvents.jsx, PublicAttainments.jsx) shows events and
# development works without signing in. Same record shapes as the dashboard.


@router.get("/events", summary="Events for the public website (unauthenticated)")
async def public_events(
    db: DbSession,
    upcoming_only: bool = Query(False, description="Only events dated today or later"),
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from app.api.routes.events import list_event_rows

    rows = await list_event_rows(db, from_date=date.today() if upcoming_only else None, limit=limit, ascending=upcoming_only)
    return [r for r in rows if r["status"] != "Cancelled"]


@router.get("/development-works", summary="Development works / attainments for the public website (unauthenticated)")
async def public_development_works(
    db: DbSession,
    mandal: str | None = Query(None),
    category: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
) -> list[dict[str, Any]]:
    from app.api.routes.development_works import list_work_rows

    return await list_work_rows(db, mandal=mandal, category=category, status_filter=status_filter)
