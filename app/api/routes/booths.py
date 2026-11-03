"""Booths page (frontend: Booths.jsx, BoothDetails.jsx, BoothModals.jsx, mockBoothsApi).

    GET    /booths                        getAll()       array of booths (search / mandal / village filters)
    GET    /booths/summary                cards: totalBooths, activeAgents, notLoggedInAgents, distinctMandals,
                                          totalVoters, mappedPct, mobileVerifiedPct, surveyedPct
    GET    /booths/export                 CSV of the (filtered) list
    GET    /booths/{id}                   getById(id)    booth + voter_list
    POST   /booths                        create (Add Booth form)
    PUT    /booths/{id}                   update
    DELETE /booths/{id}                   delete         -> {"success": true}
    POST   /booths/{id}/toggle-vote       toggleVoterVote(boothId, voterId, party, agentName)

(Bulk upload + template live in booths_bulk.py.)
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.dependencies import DbSession, page_access
from app.core.scope import resolve_scope
from app.schemas.geography import BoothCreate, BoothUpdate, VoteToggleRequest
from app.services import booth_service
from app.services.activity_service import log_activity
from app.services.voter_profile import voter_rows
from app.services.voter_service import get_voter_or_404, set_polling_mark

router = APIRouter(prefix="/booths", tags=["Booths"])

CanView = page_access("booth_management", "view")
CanDownload = page_access("booth_management", "download")
CanEdit = page_access("booth_management", "edit")
CanDelete = page_access("booth_management", "admin")

SearchFilter = Query(None, description="Search booth no, polling station, agent, mandal, village")
MandalFilter = Query(None, description="Mandal name")
VillageFilter = Query(None, description="Village name")


async def _rows(db, current_user, q, mandal, village) -> list[dict[str, Any]]:
    scope = await resolve_scope(db, current_user)
    rows = await booth_service.list_booth_rows(db, scope, q=q, mandal=mandal, village=village)
    return await booth_service.booth_rows(db, rows)


@router.get("", summary="List booths")
async def list_booths(
    db: DbSession,
    current_user: CanView,
    q: str | None = SearchFilter,
    mandal: str | None = MandalFilter,
    village: str | None = VillageFilter,
) -> list[dict[str, Any]]:
    return await _rows(db, current_user, q, mandal, village)


@router.get("/summary", summary="Booths page summary cards")
async def booth_summary(
    db: DbSession,
    current_user: CanView,
    q: str | None = SearchFilter,
    mandal: str | None = MandalFilter,
    village: str | None = VillageFilter,
) -> dict[str, Any]:
    return booth_service.booth_summary(await _rows(db, current_user, q, mandal, village))


@router.get(
    "/export",
    summary="Export the (filtered) booth list as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_booths(
    db: DbSession,
    current_user: CanDownload,
    q: str | None = SearchFilter,
    mandal: str | None = MandalFilter,
    village: str | None = VillageFilter,
) -> Response:
    content = booth_service.export_csv(await _rows(db, current_user, q, mandal, village))
    filename = f"booths_{date.today().isoformat()}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{booth_id}", summary="Get one booth with its voter list")
async def get_booth(booth_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    row = await booth_service.get_booth_row(db, booth_id, await resolve_scope(db, current_user))
    booth = (await booth_service.booth_rows(db, [row]))[0]
    booth["voter_list"] = await booth_service.booth_voter_list(db, row[0].id)
    return booth


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a booth")
async def create_booth(payload: BoothCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    booth = await booth_service.create_booth(db, payload)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="booth_added",
        module="booths",
        reference_id=booth.id,
        description=f"Added booth #{booth.booth_number} ({booth.booth_name})",
    )
    await db.commit()
    row = await booth_service.get_booth_row(db, str(booth.id))
    return (await booth_service.booth_rows(db, [row]))[0]


@router.put("/{booth_id}", summary="Update a booth")
async def update_booth(booth_id: str, payload: BoothUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    booth, _, _ = await booth_service.get_booth_row(db, booth_id, await resolve_scope(db, current_user))
    before = (await booth_service.booth_rows(db, [await booth_service.get_booth_row(db, booth_id)]))[0]
    await booth_service.update_booth(db, booth, payload)
    await db.commit()
    after = (await booth_service.booth_rows(db, [await booth_service.get_booth_row(db, booth_id)]))[0]
    keys = ("booth_no", "name", "name_te", "voters", "mandal", "village", "agent_name", "agent_mobile", "agent_alt_mobile")
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="booth_updated",
        module="booths",
        reference_id=booth.id,
        description=f"Updated booth #{after['booth_no']}",
        changes=[[k, str(before[k] or "—"), str(after[k] or "—")] for k in keys if before[k] != after[k]],
        commit=True,
    )
    return after


@router.delete("/{booth_id}", summary="Delete a booth")
async def delete_booth(booth_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    booth, _, _ = await booth_service.get_booth_row(db, booth_id, await resolve_scope(db, current_user))
    number = booth.booth_number
    await booth_service.delete_booth(db, booth)
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="booth_deleted",
        module="booths",
        reference_id=int(booth_id),
        description=f"Deleted booth #{number}",
    )
    await db.commit()
    return {"success": True}


@router.post("/{booth_id}/toggle-vote", summary="Mark / unmark a booth voter as voted")
async def toggle_vote(booth_id: str, payload: VoteToggleRequest, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    return await toggle_booth_voter_vote(db, booth_id, payload, current_user)


async def toggle_booth_voter_vote(db, booth_id: str, payload: VoteToggleRequest, current_user) -> dict[str, Any]:
    """Shared by Booth details and Polling Day: flips the voter between voted / not voted."""
    booth, _, _ = await booth_service.get_booth_row(db, booth_id, await resolve_scope(db, current_user))
    voter = await get_voter_or_404(db, payload.voter_id, include_removed=False)
    if voter.booth_id != booth.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voter is not in this booth")
    now_voted = voter.polling_status != "voted"
    set_polling_mark(
        voter,
        voted=now_voted,
        party=payload.party,
        marked_by=payload.agent_name or booth.booth_officer_name or current_user.name,
    )
    await log_activity(
        db,
        actor_id=current_user.id,
        action_type="voter_vote_marked" if now_voted else "voter_vote_unmarked",
        module="polling_day",
        reference_id=voter.id,
        description=(
            f"Marked {voter.epic_no} as voted ({payload.party}) at booth #{booth.booth_number}"
            if now_voted
            else f"Unmarked {voter.epic_no} at booth #{booth.booth_number}"
        ),
    )
    await db.commit()
    await db.refresh(voter)
    return (await voter_rows(db, [voter]))[0]
