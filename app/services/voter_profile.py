"""Voter records in the shape the dashboard uses everywhere.

The Voters page, Booth details, Polling Day, Families and the voter detail
drawer all read the same voter fields:

    id, epic_no, name, relation_type, relation_name, gender ("M" / "F" /
    "Third gender"), age, religion, caste_category, mandal, village,
    booth_no ("#256"), mobile, alt_mobile, voted_last_election ("Yes"/"No"),
    is_new_voter ("Yes"/"No"), status ("Verified"/"Pending"), dob,
    family_id, mapped, family_status, mobile_verified, mobile_status,
    survey_status, party_support, polling_status, voted_party,
    voted_party_color, marked_at, marked_by, booth_agent, photo

plus the older API fields (mandal_name, village_name, booth_number, ids,
house_no, aadhaar_masked, photo_url, created_at, updated_at).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import format_id
from app.models.families import Family, FamilyMember
from app.models.geography import Booth, Mandal, Village
from app.models.voters import Voter
from app.services.encryption_service import mask_aadhaar

IST = timezone(timedelta(hours=5, minutes=30))

GENDER_TO_UI = {"Male": "M", "Female": "F", "Other": "Third gender"}
UI_TO_GENDER = {
    "M": "Male", "MALE": "Male", "F": "Female", "FEMALE": "Female",
    "THIRD GENDER": "Other", "OTHER": "Other", "O": "Other", "T": "Other",
}

PARTY_COLORS = {
    "TDP": "#eab308",
    "BJP": "#f97316",
    "YSRCP": "#2563eb",
    "Janasena": "#ef4444",
    "Other": "#64748b",
}


def gender_to_db(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return UI_TO_GENDER.get(str(value).strip().upper(), str(value).strip())


def yes_no(value: bool | None) -> str:
    return "Yes" if value else "No"


def from_yes_no(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("yes", "y", "true", "1")


def booth_label(booth_number: str | None) -> str | None:
    if not booth_number:
        return None
    return booth_number if booth_number.startswith("#") else f"#{booth_number}"


def strip_booth_label(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip().lstrip("#").strip()
    return value or None


def format_marked_at(value: datetime | None) -> str:
    """'30 Oct, 10:50 am' in IST, or '—'."""
    if value is None:
        return "—"
    local = value.astimezone(IST)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%d %b')}, {hour}:{local.strftime('%M')} {local.strftime('%p').lower()}"


def format_dmy(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.astimezone(IST)
    return value.strftime("%d/%m/%Y")


def mobile_status(voter: Voter) -> str:
    if not voter.mobile:
        return "no_mobile"
    return "verified" if voter.mobile_verified else "not_verified"


async def survey_summaries(db: AsyncSession, voter_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Latest voter-survey result per voter (survey_status, party_support, ...).

    Filled from the Surveys module; voters without a survey are "not_done".
    """
    from app.services.survey_service import latest_survey_by_voter  # local: avoids an import cycle

    return await latest_survey_by_voter(db, voter_ids)


async def voter_rows(db: AsyncSession, voters: list[Voter]) -> list[dict[str, Any]]:
    """Frontend-shaped dicts for a list of voters, with every lookup batched."""
    if not voters:
        return []
    ids = [v.id for v in voters]
    names_stmt = (
        select(Voter.id, Mandal.name, Village.name, Booth.booth_number, Booth.booth_officer_name)
        .join(Mandal, Mandal.id == Voter.mandal_id)
        .join(Village, Village.id == Voter.village_id)
        .outerjoin(Booth, Booth.id == Voter.booth_id)
        .where(Voter.id.in_(ids))
    )
    names = {row[0]: row[1:] for row in (await db.execute(names_stmt)).all()}

    fam_stmt = select(FamilyMember.voter_id, FamilyMember.family_id, FamilyMember.relation).where(
        FamilyMember.voter_id.in_(ids)
    )
    families = {row[0]: (row[1], row[2]) for row in (await db.execute(fam_stmt)).all()}
    surveys = await survey_summaries(db, ids)

    out = []
    for v in voters:
        mandal, village, booth_number, booth_agent = names.get(v.id, (None, None, None, None))
        family_id, relation = families.get(v.id, (None, None))
        survey = surveys.get(v.id, {})
        out.append(
            {
                "id": v.id,
                "epic_no": v.epic_no,
                "name": v.name,
                "relation_type": v.relation_type,
                "relation_name": v.relation_name,
                "gender": GENDER_TO_UI.get(v.gender, v.gender),
                "age": v.age,
                "religion": v.religion,
                "caste_category": v.caste_category,
                "mandal": mandal,
                "village": village,
                "booth_no": booth_label(booth_number),
                "mobile": v.mobile,
                "alt_mobile": v.alt_mobile,
                "voted_last_election": yes_no(v.voted_last_election),
                "is_new_voter": yes_no(v.is_new_voter),
                "status": v.status,
                "dob": v.dob.isoformat() if v.dob else None,
                "photo": v.photo_url,
                # family
                "family_id": format_id("FAM", family_id),
                "family_relation": relation,
                "mapped": family_id is not None,
                "family_status": "mapped" if family_id is not None else "not_mapped",
                # mobile
                "mobile_verified": v.mobile_verified,
                "mobile_status": mobile_status(v),
                # survey
                "survey_done": bool(survey.get("survey_done")),
                "survey_status": survey.get("survey_status", "not_done"),
                "survey_type": survey.get("survey_type"),
                "survey_date": survey.get("survey_date"),
                "survey_score": survey.get("survey_score"),
                "survey_leaning": survey.get("survey_leaning"),
                "survey_feedback": survey.get("survey_feedback"),
                "party_support": survey.get("party_support") or "—",
                "party_member": survey.get("party_member"),
                "household": survey.get("household"),
                "internal_notes": survey.get("internal_notes"),
                # polling day
                "polling_status": v.polling_status,
                "voted_party": v.voted_party,
                "voted_party_color": PARTY_COLORS.get(v.voted_party) if v.voted_party else None,
                "marked_at": format_marked_at(v.marked_at),
                "marked_by": v.marked_by or "—",
                "booth_agent": booth_agent,
                # older API fields
                "mandal_id": v.mandal_id,
                "village_id": v.village_id,
                "booth_id": v.booth_id,
                "mandal_name": mandal,
                "village_name": village,
                "booth_number": booth_number,
                "house_no": v.house_no,
                "aadhaar_masked": mask_aadhaar(v.aadhaar_number),
                "photo_url": v.photo_url,
                "created_at": v.created_at,
                "updated_at": v.updated_at,
            }
        )
    return out


def removed_row(voter: Voter, village: str | None, booth_number: str | None) -> dict[str, Any]:
    """Shape of one entry in the Removed Voters list."""
    relation = " ".join(x for x in (voter.relation_type or "", voter.relation_name or "") if x).strip()
    return {
        "id": voter.id,
        "epic_no": voter.epic_no,
        "name": voter.name,
        "relation_name": relation or None,
        "booth_no": booth_label(booth_number),
        "village": village,
        "reason": voter.removal_reason,
        "details": voter.removal_details or "—",
        "removed_on": format_dmy(voter.removed_at),
        "removed_by": voter.removed_by,
    }


async def family_ids_for(db: AsyncSession, voter_ids: list[int]) -> dict[int, int]:
    if not voter_ids:
        return {}
    stmt = select(FamilyMember.voter_id, FamilyMember.family_id).where(FamilyMember.voter_id.in_(voter_ids))
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


__all__ = [
    "Family",
    "GENDER_TO_UI",
    "PARTY_COLORS",
    "booth_label",
    "family_ids_for",
    "format_dmy",
    "format_marked_at",
    "from_yes_no",
    "gender_to_db",
    "removed_row",
    "strip_booth_label",
    "voter_rows",
    "yes_no",
]
