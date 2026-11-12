from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.dependencies import DbSession
from app.core.telugu import LangQuery, localize_all
from app.models.geography import Booth, Mandal, Village
from app.models.voters import Voter
from app.schemas.contact import PublicVoterLookupOut

router = APIRouter(prefix="/public", tags=["Public"])


@router.get(
    "/voter-lookup/{epic_no}",
    response_model=PublicVoterLookupOut,
    summary="Voter-ID autofill lookup (public, unauthenticated); ?lang=te for Telugu place names",
    description="Used by the public Contact Us form to autofill Name/Mobile/Village/Mandal from an EPIC number. 404 if not found — frontend falls back to manual entry.",
)
async def public_voter_lookup(epic_no: str, db: DbSession, lang: LangQuery = "en") -> PublicVoterLookupOut:
    stmt = (
        select(Voter, Village.name, Mandal.name, Booth.booth_number, Village.name_te, Mandal.name_te)
        .join(Village, Village.id == Voter.village_id)
        .join(Mandal, Mandal.id == Voter.mandal_id)
        .outerjoin(Booth, Booth.id == Voter.booth_id)
        .where(Voter.epic_no == epic_no.strip().upper(), Voter.removed_at.is_(None))
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "EPIC number not found")
    voter, village_en, mandal_en, booth_number, village_te, mandal_te = row
    telugu = lang == "te"
    village_name = (village_te or village_en) if telugu else village_en
    mandal_name = (mandal_te or mandal_en) if telugu else mandal_en
    return PublicVoterLookupOut(
        name=voter.name,
        mobile=voter.mobile,
        village_id=voter.village_id,
        village_name=village_name,
        mandal_id=voter.mandal_id,
        mandal_name=mandal_name,
        epic_no=voter.epic_no,
        mandal=mandal_name,
        village=village_name,
        booth_no=f"#{booth_number}" if booth_number else None,
        mandal_te=mandal_te,
        village_te=village_te,
        mandal_en=mandal_en,
        village_en=village_en,
    )


# --- Public website pages ------------------------------------------------------
# The public site (PublicEvents.jsx, PublicAttainments.jsx) shows events and
# development works without signing in. Same record shapes as the dashboard.
# ?lang=te swaps text fields to Telugu (English fallback, English kept in <field>_en).

EVENT_PUBLIC_TE = ("title", "venue", "description", "chief_guest", "mandal", "village")


@router.get("/events", summary="Events for the public website (unauthenticated); ?lang=te for Telugu")
async def public_events(
    db: DbSession,
    lang: LangQuery = "en",
    upcoming_only: bool = Query(False, description="Only events dated today or later"),
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from app.api.routes.events import list_event_rows

    rows = await list_event_rows(db, from_date=date.today() if upcoming_only else None, limit=limit, ascending=upcoming_only)
    return localize_all([r for r in rows if r["status"] != "Cancelled"], lang, EVENT_PUBLIC_TE)


@router.get("/development-works", summary="Development works / attainments for the public website (unauthenticated); ?lang=te for Telugu")
async def public_development_works(
    db: DbSession,
    lang: LangQuery = "en",
    mandal: str | None = Query(None, description="Mandal name in English or Telugu"),
    category: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
) -> list[dict[str, Any]]:
    from app.api.routes.development_works import PUBLIC_TE_FIELDS, list_work_rows

    rows = await list_work_rows(db, mandal=mandal, category=category, status_filter=status_filter)
    return localize_all(rows, lang, PUBLIC_TE_FIELDS)
