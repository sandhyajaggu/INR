"""Public Enquiry Requests + Election Pulse (frontend: Contact.js, PublicEnquiryRequests.jsx,
PublicEnquiryDrawer, mockPublicEnquiryApi).

    POST   /public/enquiries                      submitEnquiry(data)    public Contact page, no sign-in
    GET    /public-enquiries                      getEnquiries()         array (q / status / type filters)
    GET    /public-enquiries/summary              cards: total, new, inProgress, resolved
    GET    /public-enquiries/election-pulse       getElectionPulse(timeframe = "30" | "90" | "all")
    GET    /public-enquiries/{id}
    PATCH  /public-enquiries/{id}/status          updateStatus(id, status)
    DELETE /public-enquiries/{id}                 deleteEnquiry(id) -> {"success": true}

Enquiry ids are "KDK-<n>". Record shape: id, photo, voterId, constituency,
citizenName, enquiryType, mandal, village, mobile, email, message,
voiceRecording ({duration, url} or null), receivedAt, status, feedback.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, or_, select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.models.engagement import PublicEnquiry
from app.models.voters import Voter
from app.schemas.common import validate_mobile_number
from app.services.activity_service import log_activity

router = APIRouter(prefix="/public-enquiries", tags=["Public Enquiry Requests"])
public_router = APIRouter(prefix="/public", tags=["Public"])

CanView = page_access("public_enquiry", "view")
CanEdit = page_access("public_enquiry", "edit")
CanDelete = page_access("public_enquiry", "admin")

PREFIX = "KDK"
STATUSES = ("New", "In Progress", "Resolved")
HOME_CONSTITUENCY = "kandukur"
MANDALS = ("Kandukur", "Lingasamudram", "Gudluru", "Ulavapadu", "Voletivaripalem")
MAX_INLINE_FILE = 12 * 1024 * 1024  # base64 data URLs from the public form


class VoiceRecording(BaseModel):
    duration: str | None = None
    url: str | None = None


class Feedback(BaseModel):
    model_config = ConfigDict(extra="allow")

    satisfiedWithMLA: str | None = None
    easeOfMeeting: str | None = None
    villageDeveloped: str | None = None
    schemesReaching: str | None = None
    voteToday: str | None = None
    expectToWin: str | None = None
    whatMattersMost: str | None = None
    likelyToVote: str | None = None
    suggestion: str | None = None


class EnquirySubmit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    photo: str | None = Field(default=None, max_length=MAX_INLINE_FILE)
    voterId: str | None = None
    constituency: str | None = "Kandukur"
    citizenName: str = Field(min_length=1, max_length=150)
    enquiryType: str = Field(default="General Feedback", min_length=1, max_length=100)
    mandal: str | None = None
    village: str | None = None
    mobile: str
    email: EmailStr | None = None
    message: str | None = Field(default=None, max_length=5000)
    voiceRecording: VoiceRecording | None = None
    feedback: Feedback | None = None

    @field_validator("email", "voterId", "mandal", "village", "photo", mode="before")
    @classmethod
    def _blank(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("mobile", mode="before")
    @classmethod
    def _mobile(cls, v: object) -> str:
        value = validate_mobile_number(v)
        if value is None:
            raise ValueError("mobile is required")
        return value


class StatusUpdate(BaseModel):
    status: str

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        for s in STATUSES:
            if s.lower() == str(v or "").strip().lower():
                return s
        raise ValueError("status must be New, In Progress or Resolved")


def enquiry_row(e: PublicEnquiry) -> dict[str, Any]:
    voice = None
    if e.voice_url or e.voice_duration:
        voice = {"duration": e.voice_duration, "url": e.voice_url or ""}
    return {
        "id": format_id(PREFIX, e.id),
        "photo": e.photo_url,
        "voterId": e.epic_no or "",
        "constituency": e.constituency,
        "citizenName": e.citizen_name,
        "enquiryType": e.enquiry_type,
        "mandal": e.mandal,
        "village": e.village,
        "mobile": e.mobile,
        "email": e.email,
        "message": e.message,
        "voiceRecording": voice,
        "receivedAt": e.received_at,
        "status": e.status,
        "feedback": e.feedback,
        "matchedInVoterList": e.matched_in_voter_list,
    }


async def _get(db, enquiry_id: str) -> PublicEnquiry:
    obj = await db.get(PublicEnquiry, parse_id(enquiry_id, label="Enquiry"), populate_existing=True)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enquiry not found")
    return obj


@public_router.post("/enquiries", status_code=status.HTTP_201_CREATED, summary="Submit an enquiry from the public Contact page")
async def submit_enquiry(payload: EnquirySubmit, db: DbSession) -> dict[str, Any]:
    voter = None
    if payload.voterId:
        voter = (
            await db.execute(select(Voter).where(Voter.epic_no == payload.voterId.strip().upper()))
        ).scalar_one_or_none()
    feedback = payload.feedback.model_dump(exclude_none=True) if payload.feedback else None
    is_home = (payload.constituency or "").strip().lower() == HOME_CONSTITUENCY
    obj = PublicEnquiry(
        citizen_name=payload.citizenName.strip(),
        epic_no=payload.voterId.strip().upper() if payload.voterId else None,
        voter_id=voter.id if voter else None,
        constituency=payload.constituency,
        enquiry_type=payload.enquiryType,
        mandal=payload.mandal,
        village=payload.village,
        mobile=payload.mobile,
        email=payload.email,
        message=payload.message,
        photo_url=payload.photo,
        voice_url=(payload.voiceRecording.url or None) if payload.voiceRecording else None,
        voice_duration=payload.voiceRecording.duration if payload.voiceRecording else None,
        feedback=feedback if is_home else None,
        matched_in_voter_list=voter is not None,
    )
    db.add(obj)
    await db.commit()
    return {"success": True, "enquiry": enquiry_row(await _get(db, str(obj.id)))}


@router.get("", summary="List enquiries (newest first)")
async def get_enquiries(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    enquiry_type: str | None = Query(None, alias="type"),
    limit: int = Query(1000, ge=1, le=10000),
) -> list[dict[str, Any]]:
    stmt = select(PublicEnquiry)
    if status_filter:
        stmt = stmt.where(PublicEnquiry.status == status_filter)
    if enquiry_type:
        stmt = stmt.where(PublicEnquiry.enquiry_type == enquiry_type)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                PublicEnquiry.citizen_name.ilike(term),
                PublicEnquiry.mobile.ilike(term),
                PublicEnquiry.epic_no.ilike(term),
                PublicEnquiry.enquiry_type.ilike(term),
                PublicEnquiry.mandal.ilike(term),
                PublicEnquiry.village.ilike(term),
                PublicEnquiry.message.ilike(term),
            )
        )
    rows = (await db.execute(stmt.order_by(PublicEnquiry.received_at.desc()).limit(limit))).scalars().all()
    return [enquiry_row(e) for e in rows]


@router.get("/summary", summary="Public Enquiry page summary cards")
async def enquiry_summary(db: DbSession, current_user: CanView) -> dict[str, int]:
    counts = dict((await db.execute(select(PublicEnquiry.status, func.count()).group_by(PublicEnquiry.status))).all())
    return {
        "total": sum(counts.values()),
        "new": counts.get("New", 0),
        "inProgress": counts.get("In Progress", 0),
        "resolved": counts.get("Resolved", 0),
    }


def _pct(part: float, whole: float) -> int:
    return round(part * 100 / whole) if whole else 0


def _score(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    total = sum(e["_w"] for e in entries)
    if not total:
        return None
    vote = sum(e["_w"] for e in entries if _votes_mla(e))
    win = sum(e["_w"] for e in entries if e.get("expectToWin") == "TDP")
    sat = sum(e["_w"] for e in entries if e.get("satisfiedWithMLA") in ("Very satisfied", "Satisfied"))
    certain = sum(e["_w"] for e in entries if e.get("likelyToVote") == "Certainly")
    would, expect, satisfied = _pct(vote, total), _pct(win, total), _pct(sat, total)
    return {
        "total": total,
        "wouldVotePct": would,
        "expectWinPct": expect,
        "satisfiedPct": satisfied,
        "certainlyVotePct": _pct(certain, total),
        # 45% would vote + 30% expect to win + 25% satisfied
        "winScore": round(0.45 * would + 0.30 * expect + 0.25 * satisfied),
    }


def _votes_mla(entry: dict[str, Any]) -> bool:
    vote = entry.get("voteToday") or ""
    return "Inturi Nageswara Rao" in vote or "TDP" in vote


@router.get("/election-pulse", summary="Election Pulse from the voter feedback")
async def election_pulse(
    db: DbSession,
    current_user: CanView,
    timeframe: str = Query("90", pattern="^(30|90|all)$"),
) -> dict[str, Any]:
    """Uses each mobile number's latest Kandukur feedback. Answers from people found in the voter
    list count fully; others count half."""
    now = datetime.now(timezone.utc)
    stmt = select(PublicEnquiry).where(
        PublicEnquiry.feedback.is_not(None), func.lower(PublicEnquiry.constituency) == HOME_CONSTITUENCY
    )
    if timeframe != "all":
        stmt = stmt.where(PublicEnquiry.received_at >= now - timedelta(days=int(timeframe)))
    latest: dict[str, PublicEnquiry] = {}
    for e in (await db.execute(stmt.order_by(PublicEnquiry.received_at.asc()))).scalars().all():
        latest[e.mobile] = e
    entries = [
        {**(e.feedback or {}), "_w": 1.0 if e.matched_in_voter_list else 0.5, "_mandal": e.mandal, "_at": e.received_at,
         "_matched": e.matched_in_voter_list}
        for e in latest.values()
    ]
    total_answers = len(entries)
    empty = {
        "totalAnswers": 0, "inVoterListCount": 0, "hasEnoughData": False, "winScore": None, "wouldVotePct": None,
        "satisfiedPct": None, "certainlyVotePct": None, "todayVoteBreakdown": [], "expectedWinnerBreakdown": [],
        "weeklyTrends": [], "mandalBreakdown": [],
    }
    score = _score(entries)
    if score is None:
        return empty
    total_w = score["total"]

    def share(pred) -> int:
        return _pct(sum(e["_w"] for e in entries if pred(e)), total_w)

    ysrcp = share(lambda e: not _votes_mla(e) and "YSRCP" in (e.get("voteToday") or ""))
    jsp = share(lambda e: not _votes_mla(e) and "Janasena" in (e.get("voteToday") or ""))
    today = [
        {"party": "Inturi Nageswara Rao (TDP)", "pct": score["wouldVotePct"]},
        {"party": "YSRCP candidate", "pct": ysrcp},
        {"party": "Janasena", "pct": jsp},
        {"party": "Other / Not decided", "pct": max(0, 100 - score["wouldVotePct"] - ysrcp - jsp)},
    ]
    w_ysrcp = share(lambda e: e.get("expectToWin") == "YSRCP")
    w_jsp = share(lambda e: e.get("expectToWin") == "Janasena")
    expected = [
        {"party": "TDP", "pct": score["expectWinPct"]},
        {"party": "YSRCP", "pct": w_ysrcp},
        {"party": "Janasena", "pct": w_jsp},
        {"party": "Can't say", "pct": max(0, 100 - score["expectWinPct"] - w_ysrcp - w_jsp)},
    ]
    mandal_rows = []
    for mandal in MANDALS:
        group = [e for e in entries if (e["_mandal"] or "").lower() == mandal.lower()]
        total = sum(e["_w"] for e in group)
        mandal_rows.append(
            {"mandal": mandal, "pct": _pct(sum(e["_w"] for e in group if _votes_mla(e)), total) if total else None,
             "answers": len(group)}
        )
    mandal_rows.sort(key=lambda r: (r["pct"] is None, r["pct"] or 0))

    window_start = now - timedelta(weeks=12)
    trends = []
    for week in (1, 4, 8, 12):
        cutoff = window_start + timedelta(weeks=week)
        s = _score([e for e in entries if e["_at"] <= cutoff])
        trends.append({"week": f"W{week}", "score": s["winScore"] if s else None})

    return {
        "totalAnswers": total_answers,
        "inVoterListCount": sum(1 for e in entries if e["_matched"]),
        "hasEnoughData": total_answers >= 3,
        "winScore": score["winScore"],
        "wouldVotePct": score["wouldVotePct"],
        "satisfiedPct": score["satisfiedPct"],
        "certainlyVotePct": score["certainlyVotePct"],
        "todayVoteBreakdown": today,
        "expectedWinnerBreakdown": expected,
        "weeklyTrends": trends,
        "mandalBreakdown": mandal_rows,
    }


@router.get("/{enquiry_id}", summary="Get one enquiry")
async def get_enquiry(enquiry_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    return enquiry_row(await _get(db, enquiry_id))


@router.patch("/{enquiry_id}/status", summary="Change an enquiry's status")
async def update_enquiry_status(
    enquiry_id: str, payload: StatusUpdate, db: DbSession, current_user: CanEdit
) -> dict[str, Any]:
    obj = await _get(db, enquiry_id)
    old = obj.status
    obj.status = payload.status
    await log_activity(
        db, actor_id=current_user.id, action_type="enquiry_status_changed", module="Public Enquiry",
        reference_id=obj.id, description=f"Enquiry {format_id(PREFIX, obj.id)}: {old} → {payload.status}",
        changes=[["status", old, payload.status]],
    )
    await db.commit()
    return enquiry_row(await _get(db, enquiry_id))


@router.delete("/{enquiry_id}", summary="Delete an enquiry")
async def delete_enquiry(enquiry_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, enquiry_id)
    await log_activity(
        db, actor_id=current_user.id, action_type="enquiry_deleted", module="Public Enquiry",
        reference_id=obj.id, description=f"Deleted enquiry {format_id(PREFIX, obj.id)} from {obj.citizen_name}",
    )
    await db.delete(obj)
    await db.commit()
    return {"success": True}
