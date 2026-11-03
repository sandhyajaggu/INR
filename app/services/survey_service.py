"""Voter survey lookups shared with other modules (voter profile, booths, families, birthdays)."""

from datetime import timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import VoterSurvey
from app.models.voters import Voter

IST = timezone(timedelta(hours=5, minutes=30))


def survey_score(answers: list[dict[str, Any]] | None, added: list[dict[str, Any]] | None = None) -> str:
    """"5/10 Yes" when the survey has Yes/No questions, else "24 answers"."""
    items = [a for a in [*(answers or []), *(added or [])] if str(a.get("answer") or "").strip()]
    yes_no = [a for a in items if str(a.get("answer")).strip().lower() in ("yes", "no")]
    if yes_no:
        yes = sum(1 for a in yes_no if str(a.get("answer")).strip().lower() == "yes")
        return f"{yes}/{len(yes_no)} Yes"
    return f"{len(items)} answers"


def summary_of(s: VoterSurvey) -> dict[str, Any]:
    feedback = (s.feedback or "").strip()
    return {
        "survey_done": True,
        "survey_id": s.id,
        "survey_status": feedback.lower() if feedback.lower() in ("positive", "negative") else "done",
        "survey_type": s.survey_type,
        "survey_date": s.created_at.astimezone(IST).strftime("%d/%m/%Y") if s.created_at else None,
        "survey_score": survey_score(s.answers, s.added_questions),
        "survey_leaning": s.party_support,
        "survey_feedback": feedback or None,
        "party_support": s.party_support,
        "party_member": s.party_member,
        "household": s.household_status,
        "internal_notes": s.field_notes,
        "booth_agent": s.surveyed_by_name,
    }


async def latest_survey_by_voter(db: AsyncSession, voter_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Latest voter survey per voter id. Voters with no survey are absent from the result."""
    if not voter_ids:
        return {}
    latest_ids = (
        select(func.max(VoterSurvey.id))
        .where(VoterSurvey.voter_id.in_(voter_ids))
        .group_by(VoterSurvey.voter_id)
    )
    rows = (await db.execute(select(VoterSurvey).where(VoterSurvey.id.in_(latest_ids)))).scalars().all()
    return {s.voter_id: summary_of(s) for s in rows}


async def surveyed_counts_by_booth(db: AsyncSession, booth_ids: list[int]) -> dict[int, int]:
    """Number of distinct surveyed (active) voters per booth id."""
    if not booth_ids:
        return {}
    stmt = (
        select(Voter.booth_id, func.count(func.distinct(VoterSurvey.voter_id)))
        .join(Voter, Voter.id == VoterSurvey.voter_id)
        .where(Voter.booth_id.in_(booth_ids), Voter.removed_at.is_(None))
        .group_by(Voter.booth_id)
    )
    return dict((await db.execute(stmt)).all())
