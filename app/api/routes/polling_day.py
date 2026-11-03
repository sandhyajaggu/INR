"""Polling Day (frontend: PollingDay.jsx, PolingDayDetails.jsx, mockPollingDayApi).

    GET  /polling-day/booths                     getBooths()       booth_no, name, voters, votes_polled, party_mix, leading
    GET  /polling-day/summary                    cards: booths, voters, votesPolled, turnoutPct, partyTotals
    GET  /polling-day/booths/{id}                getBoothById(id)  + voter_list
    POST /polling-day/booths/{id}/toggle-vote    toggleVoterVote(boothId, voterId, party, agentName)

Access follows the Booth Management page.
"""

from typing import Any

from fastapi import APIRouter, Query

from app.api.routes.booths import toggle_booth_voter_vote
from app.core.dependencies import DbSession, page_access
from app.core.scope import resolve_scope
from app.schemas.geography import VoteToggleRequest
from app.services import booth_service

router = APIRouter(prefix="/polling-day", tags=["Polling Day"])

CanView = page_access("booth_management", "view")
CanEdit = page_access("booth_management", "edit")


async def _polling_rows(db, current_user, q, mandal) -> list[dict[str, Any]]:
    scope = await resolve_scope(db, current_user)
    rows = await booth_service.list_booth_rows(db, scope, q=q, mandal=mandal)
    return await booth_service.polling_rows(db, rows)


@router.get("/booths", summary="Polling Day booth list")
async def get_polling_booths(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None),
    mandal: str | None = Query(None),
) -> list[dict[str, Any]]:
    return await _polling_rows(db, current_user, q, mandal)


@router.get("/summary", summary="Polling Day summary cards")
async def get_polling_summary(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None),
    mandal: str | None = Query(None),
) -> dict[str, Any]:
    rows = await _polling_rows(db, current_user, q, mandal)
    voters = sum(r["voters"] for r in rows)
    polled = sum(r["votes_polled"] for r in rows)
    party_totals: dict[str, int] = {}
    for r in rows:
        for party, n in r["party_counts"].items():
            party_totals[party] = party_totals.get(party, 0) + n
    return {
        "booths": len(rows),
        "voters": voters,
        "votesPolled": polled,
        "turnoutPct": round(polled * 100 / voters) if voters else 0,
        "partyTotals": party_totals,
    }


@router.get("/booths/{booth_id}", summary="One Polling Day booth with its voter list")
async def get_polling_booth(booth_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    row = await booth_service.get_booth_row(db, booth_id, await resolve_scope(db, current_user))
    booth = (await booth_service.polling_rows(db, [row]))[0]
    booth["voter_list"] = await booth_service.booth_voter_list(db, row[0].id)
    return booth


@router.post("/booths/{booth_id}/toggle-vote", summary="Mark / unmark a voter as voted")
async def toggle_polling_vote(
    booth_id: str, payload: VoteToggleRequest, db: DbSession, current_user: CanEdit
) -> dict[str, Any]:
    return await toggle_booth_voter_vote(db, booth_id, payload, current_user)
