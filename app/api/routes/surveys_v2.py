"""Surveys & Campaigns page (frontend: Surveys.jsx, SurveyModals.jsx, NewSurvey.jsx,
VoterSurveyModal in VoterActionModals.jsx, mockSurveysApi).

Voter surveys
    GET    /voter-surveys                         getVoterSurveys()   (q / type / feedback filters)
    GET    /voter-surveys/default-questions       DEFAULT_SURVEY_QUESTIONS
    GET    /voter-surveys/summary                 cards
    POST   /voter-surveys                         submit a door-to-door survey (VoterSurveyModal payload)
    GET    /voter-surveys/{id}                    full survey with answers
    DELETE /voter-surveys/{id}
Campaigns by channel
    GET    /survey-campaigns                      getCampaigns()
    POST   /survey-campaigns                      createSurvey {name, channel, feedback, status}
    POST   /survey-campaigns/publish              NewSurvey "Publish" {name, questions, channels, post_text}
    PUT    /survey-campaigns/{id}                 updateCampaign(id, data)
    POST   /survey-campaigns/{id}/responses       recordChannelResponse(id, isPositive)  body {positive: bool}
    DELETE /survey-campaigns/{id}
War Room
    GET    /war-room-alerts                       getWarRoomAlerts()
    PATCH  /war-room-alerts/{id}                  {status, resolution_notes}

Ids: VS-<n>, CAMP-<n>, WR-<n>. A survey whose escalation is "VIP alert" or
"Grievance fix" raises a War Room alert. Part A answers (religion, caste,
mobile, DOB) are saved onto the voter.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.models.engagement import SurveyCampaign, VoterSurvey, WarRoomAlert
from app.models.voters import Voter
from app.services.activity_service import log_activity
from app.services.survey_service import IST, survey_score
from app.services.voter_profile import voter_rows
from app.services.voter_service import get_voter_or_404

voter_surveys_router = APIRouter(prefix="/voter-surveys", tags=["Surveys"])
campaigns_router = APIRouter(prefix="/survey-campaigns", tags=["Surveys"])
war_room_router = APIRouter(prefix="/war-room-alerts", tags=["Surveys"])

CanView = page_access("surveys_campaigns", "view")
CanEdit = page_access("surveys_campaigns", "edit")
CanDelete = page_access("surveys_campaigns", "admin")

CAMPAIGN_STATUSES = ("Running", "Paused", "Closed")
ESCALATING = {"vip alert", "grievance fix"}
WAR_ROOM_STATUSES = ("Pending Action", "In Progress", "Resolved")

DEFAULT_SURVEY_QUESTIONS = [
    {"id": 1, "text": "Does your family get government welfare scheme benefits?", "type": "Choice",
     "options": "Yes, No, Applied, waiting", "required": True},
    {"id": 2, "text": "If elections were held today, which party would you vote for?", "type": "Choice",
     "options": "TDP, YSRCP, Janasena, BJP, Congress, Other, Prefer not to say", "required": False},
]

VOTER_FIELDS = ("id", "epic_no", "name", "relation_type", "relation_name", "gender", "age", "dob", "caste_category",
                "religion", "mobile", "village", "mandal", "booth_no", "voted_last_election")


def _dmy(dt_value: datetime | None) -> str | None:
    return dt_value.astimezone(IST).strftime("%d/%m/%Y") if dt_value else None


# --- voter surveys ----------------------------------------------------------------


class QA(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | str | None = None
    question: str | None = None
    answer: Any = None


class PartA(BaseModel):
    model_config = ConfigDict(extra="ignore")

    religion: str | None = None
    caste: str | None = None
    mobile: str | None = None
    noMobile: bool = False
    dob: str | None = None


class InternalNotes(BaseModel):
    model_config = ConfigDict(extra="ignore")

    householdStatus: str | None = None
    escalation: str | None = None
    fieldNotes: str | None = None


class VoterSurveySubmit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    voterId: int | str | None = None
    epic_no: str | None = None
    surveyType: str = Field(min_length=1, max_length=100)
    partA: PartA = PartA()
    answers: list[QA] = []
    addedQuestions: list[QA] = []
    partySupport: str | None = None
    partyMember: str | None = None
    memberParty: str | None = None
    membershipId: str | None = None
    internalNotes: InternalNotes = InternalNotes()
    feedback: str | None = None


async def survey_list_rows(db, surveys: list[VoterSurvey]) -> list[dict[str, Any]]:
    voters = {v.id: v for v in (await db.execute(select(Voter).where(Voter.id.in_({s.voter_id for s in surveys} or {-1})))).scalars().all()}
    profiles = {r["id"]: r for r in await voter_rows(db, list(voters.values()))}
    out = []
    for s in surveys:
        profile = profiles.get(s.voter_id, {})
        out.append(
            {
                "id": format_id("VS", s.id),
                "survey_id": format_id("VS", s.id),
                "date": _dmy(s.created_at),
                "survey_type": s.survey_type,
                "voter": {k: profile.get(k) for k in VOTER_FIELDS},
                "booth": profile.get("booth_no"),
                "booth_agent": s.surveyed_by_name,
                "answers": survey_score(s.answers, s.added_questions),
                "feedback": s.feedback,
                "party_support": s.party_support or "—",
                "party_member": s.party_member or "—",
                "household": s.household_status or "—",
                "escalation": s.escalation or "—",
            }
        )
    return out


@voter_surveys_router.get("/default-questions", summary="Default questions asked in every survey")
async def default_questions(current_user: CanView) -> list[dict[str, Any]]:
    return DEFAULT_SURVEY_QUESTIONS


@voter_surveys_router.get("/summary", summary="Surveys page cards")
async def surveys_summary(db: DbSession, current_user: CanView) -> dict[str, int]:
    total, positive, negative, voters = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(func.lower(VoterSurvey.feedback) == "positive"),
                func.count().filter(func.lower(VoterSurvey.feedback) == "negative"),
                func.count(func.distinct(VoterSurvey.voter_id)),
            )
        )
    ).one()
    campaigns = (await db.execute(select(func.count()).select_from(SurveyCampaign).where(SurveyCampaign.status == "Running"))).scalar_one()
    alerts = (await db.execute(select(func.count()).select_from(WarRoomAlert).where(WarRoomAlert.status != "Resolved"))).scalar_one()
    return {
        "totalSurveys": total, "positive": positive, "negative": negative, "votersSurveyed": voters,
        "runningCampaigns": campaigns, "openWarRoomAlerts": alerts,
    }


@voter_surveys_router.get("", summary="List voter surveys (newest first)")
async def get_voter_surveys(
    db: DbSession,
    current_user: CanView,
    q: str | None = Query(None, description="Voter name / EPIC"),
    survey_type: str | None = Query(None, alias="type"),
    feedback: str | None = Query(None, pattern="^(Positive|Negative)$"),
    limit: int = Query(1000, ge=1, le=10000),
) -> list[dict[str, Any]]:
    stmt = select(VoterSurvey).join(Voter, Voter.id == VoterSurvey.voter_id)
    if survey_type:
        stmt = stmt.where(VoterSurvey.survey_type == survey_type)
    if feedback:
        stmt = stmt.where(func.lower(VoterSurvey.feedback) == feedback.lower())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Voter.name.ilike(term), Voter.epic_no.ilike(term)))
    surveys = list((await db.execute(stmt.order_by(VoterSurvey.id.desc()).limit(limit))).scalars().all())
    return await survey_list_rows(db, surveys)


@voter_surveys_router.post("", status_code=status.HTTP_201_CREATED, summary="Submit a voter survey")
async def submit_voter_survey(payload: VoterSurveySubmit, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    ref = payload.epic_no or payload.voterId
    if ref is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "voterId or epic_no is required")
    voter = await get_voter_or_404(db, str(ref), include_removed=False)

    part_a = payload.partA
    if part_a.religion:
        voter.religion = part_a.religion
    if part_a.caste:
        voter.caste_category = part_a.caste
    if part_a.noMobile:
        voter.mobile = None
    elif part_a.mobile and part_a.mobile.strip():
        voter.mobile = part_a.mobile.strip()
    if part_a.dob:
        try:
            voter.dob = date.fromisoformat(part_a.dob[:10])
        except ValueError:
            pass

    notes = payload.internalNotes
    survey = VoterSurvey(
        voter_id=voter.id,
        survey_type=payload.surveyType,
        part_a=part_a.model_dump(),
        answers=[a.model_dump() for a in payload.answers],
        added_questions=[a.model_dump() for a in payload.addedQuestions],
        party_support=payload.partySupport,
        party_member=payload.partyMember,
        member_party=payload.memberParty or None,
        membership_id=payload.membershipId or None,
        household_status=notes.householdStatus,
        escalation=notes.escalation,
        field_notes=notes.fieldNotes,
        feedback=payload.feedback,
        surveyed_by=current_user.id,
        surveyed_by_name=current_user.name,
    )
    db.add(survey)
    await db.flush()
    if (notes.escalation or "").strip().lower() in ESCALATING:
        db.add(
            WarRoomAlert(
                voter_id=voter.id, survey_id=survey.id, escalation=notes.escalation, household=notes.householdStatus,
                field_notes=notes.fieldNotes, booth_agent=current_user.name,
            )
        )
    await log_activity(
        db, actor_id=current_user.id, action_type="voter_survey_added", module="Surveys", reference_id=survey.id,
        description=f"Surveyed voter {voter.epic_no} ({payload.surveyType})",
    )
    await db.commit()
    return (await survey_list_rows(db, [survey]))[0]


@voter_surveys_router.get("/{survey_id}", summary="One voter survey with all answers")
async def get_voter_survey(survey_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    s = await db.get(VoterSurvey, parse_id(survey_id, label="Survey"))
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Survey not found")
    row = (await survey_list_rows(db, [s]))[0]
    return {
        **row,
        "partA": s.part_a,
        "answerList": s.answers,
        "addedQuestions": s.added_questions,
        "memberParty": s.member_party,
        "membershipId": s.membership_id,
        "fieldNotes": s.field_notes,
    }


@voter_surveys_router.delete("/{survey_id}", summary="Delete a voter survey")
async def delete_voter_survey(survey_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    s = await db.get(VoterSurvey, parse_id(survey_id, label="Survey"))
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Survey not found")
    await db.delete(s)
    await db.commit()
    return {"success": True}


# --- campaigns ------------------------------------------------------------------------


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    channel: str = Field(default="WhatsApp", max_length=30)
    feedback: str | None = None
    status: str = "Running"
    target: int | None = Field(default=None, ge=0)
    closes_at: datetime | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        for s in CAMPAIGN_STATUSES:
            if s.lower() == str(v or "Running").strip().lower():
                return s
        raise ValueError("status must be Running, Paused or Closed")


class CampaignUpdate(CampaignCreate):
    responses: int | None = Field(default=None, ge=0)
    positive: int | None = Field(default=None, ge=0)
    negative: int | None = Field(default=None, ge=0)


class ChannelSchedule(BaseModel):
    enabled: bool = False
    date: str | None = None
    time: str | None = None


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    questions: list[dict[str, Any]] = []
    channels: dict[str, ChannelSchedule] = {}
    post_text: str | None = Field(default=None, alias="postText")


class ResponseRecord(BaseModel):
    positive: bool


CHANNEL_LABELS = {"facebook": "Facebook", "instagram": "Instagram", "twitter": "Twitter (X)", "youtube": "YouTube",
                  "whatsapp": "WhatsApp"}


def _closes_label(closes_at: datetime | None) -> str | None:
    if closes_at is None:
        return None
    local = closes_at.astimezone(IST)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"closes {local.strftime('%d %b')}, {hour}:{local.strftime('%M')} {local.strftime('%p').lower()}"


def campaign_row(c: SurveyCampaign) -> dict[str, Any]:
    base = settings.public_site_url.rstrip("/")
    return {
        "id": format_id("CAMP", c.id),
        "name": c.name,
        "channel": c.channel,
        "responses": c.responses,
        "target": c.target,
        "positive": c.positive,
        "negative": c.negative,
        "status": c.status,
        "feedback": c.feedback_filter,
        "closes_on": _closes_label(c.closes_at),
        "closesAt": c.closes_at,
        "link": f"{base}/survey/SV-{c.id}",
        "questions": c.questions or [],
        "post_text": c.post_text,
        "createdAt": c.created_at,
    }


async def _campaign(db, campaign_id: str) -> SurveyCampaign:
    c = await db.get(SurveyCampaign, parse_id(campaign_id, label="Campaign"), populate_existing=True)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return c


@campaigns_router.get("", summary="Survey campaigns by channel")
async def get_campaigns(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    rows = (await db.execute(select(SurveyCampaign).order_by(SurveyCampaign.id.desc()))).scalars().all()
    return [campaign_row(c) for c in rows]


@campaigns_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a survey campaign")
async def create_campaign(payload: CampaignCreate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    c = SurveyCampaign(
        name=payload.name, channel=payload.channel, feedback_filter=payload.feedback, status=payload.status,
        target=payload.target or 1000, starts_at=datetime.now(timezone.utc),
        closes_at=payload.closes_at or datetime.now(timezone.utc) + timedelta(days=14),
        questions=DEFAULT_SURVEY_QUESTIONS, created_by=current_user.id,
    )
    db.add(c)
    await db.flush()
    await log_activity(db, actor_id=current_user.id, action_type="survey_campaign_added", module="Surveys",
                       reference_id=c.id, description=f"Created survey campaign {c.name} ({c.channel})")
    await db.commit()
    return campaign_row(await _campaign(db, str(c.id)))


@campaigns_router.post("/publish", status_code=status.HTTP_201_CREATED, summary="Publish a survey to the chosen channels")
async def publish_survey(payload: PublishRequest, db: DbSession, current_user: CanEdit) -> list[dict[str, Any]]:
    enabled = {k: v for k, v in payload.channels.items() if v.enabled}
    if not enabled:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one channel")
    questions = [*DEFAULT_SURVEY_QUESTIONS, *payload.questions]
    created = []
    for key, sched in enabled.items():
        starts = datetime.now(timezone.utc)
        if sched.date:
            try:
                starts = datetime.fromisoformat(f"{sched.date}T{sched.time or '09:00'}").replace(tzinfo=IST)
            except ValueError:
                pass
        c = SurveyCampaign(
            name=payload.name, channel=CHANNEL_LABELS.get(key.lower(), key), status="Running", target=1000,
            starts_at=starts, closes_at=starts + timedelta(days=14), questions=questions,
            post_text=payload.post_text, created_by=current_user.id,
        )
        db.add(c)
        created.append(c)
    await db.flush()
    await log_activity(db, actor_id=current_user.id, action_type="survey_published", module="Surveys", reference_id=None,
                       description=f"Published survey {payload.name} to {', '.join(c.channel for c in created)}")
    await db.commit()
    return [campaign_row(await _campaign(db, str(c.id))) for c in created]


@campaigns_router.put("/{campaign_id}", summary="Edit a survey campaign")
async def update_campaign(campaign_id: str, payload: CampaignUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    c = await _campaign(db, campaign_id)
    data = payload.model_dump(exclude_unset=True)
    mapping = {"feedback": "feedback_filter"}
    for key, value in data.items():
        if value is None and key in ("target", "responses", "positive", "negative"):
            continue
        setattr(c, mapping.get(key, key), value)
    await log_activity(db, actor_id=current_user.id, action_type="survey_campaign_updated", module="Surveys",
                       reference_id=c.id, description=f"Updated survey campaign {c.name}")
    await db.commit()
    return campaign_row(await _campaign(db, campaign_id))


@campaigns_router.post("/{campaign_id}/responses", summary="Record one response (positive / negative)")
async def record_response(campaign_id: str, payload: ResponseRecord, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    c = await _campaign(db, campaign_id)
    c.responses += 1
    if payload.positive:
        c.positive += 1
    else:
        c.negative += 1
    await db.commit()
    return campaign_row(await _campaign(db, campaign_id))


@campaigns_router.delete("/{campaign_id}", summary="Delete a survey campaign")
async def delete_campaign(campaign_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    c = await _campaign(db, campaign_id)
    await db.delete(c)
    await db.commit()
    return {"success": True}


# --- war room -----------------------------------------------------------------------------


class WarRoomUpdate(BaseModel):
    status: str
    resolution_notes: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        for s in WAR_ROOM_STATUSES:
            if s.lower() == str(v or "").strip().lower():
                return s
        raise ValueError(f"status must be one of: {', '.join(WAR_ROOM_STATUSES)}")


async def war_room_rows(db, alerts: list[WarRoomAlert]) -> list[dict[str, Any]]:
    voters = list((await db.execute(select(Voter).where(Voter.id.in_({a.voter_id for a in alerts} or {-1})))).scalars().all())
    profiles = {r["id"]: r for r in await voter_rows(db, voters)}
    out = []
    for a in alerts:
        p = profiles.get(a.voter_id, {})
        out.append(
            {
                "id": format_id("WR", a.id),
                "raised": _dmy(a.raised_at),
                "voter": {k: p.get(k) for k in VOTER_FIELDS},
                "booth_village": " · ".join(x for x in (p.get("booth_no"), p.get("village")) if x),
                "escalation": a.escalation,
                "household": a.household,
                "field_notes": a.field_notes,
                "booth_agent": a.booth_agent,
                "status": a.status,
                "resolution_notes": a.resolution_notes,
                "survey_id": format_id("VS", a.survey_id),
            }
        )
    return out


@war_room_router.get("", summary="War Room alerts (open first)")
async def get_war_room_alerts(
    db: DbSession, current_user: CanView, status_filter: str | None = Query(None, alias="status")
) -> list[dict[str, Any]]:
    stmt = select(WarRoomAlert)
    if status_filter:
        stmt = stmt.where(WarRoomAlert.status == status_filter)
    stmt = stmt.order_by((WarRoomAlert.status == "Resolved").asc(), WarRoomAlert.raised_at.desc())
    return await war_room_rows(db, list((await db.execute(stmt)).scalars().all()))


@war_room_router.patch("/{alert_id}", summary="Update a War Room alert's status")
async def update_war_room_alert(alert_id: str, payload: WarRoomUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    a = await db.get(WarRoomAlert, parse_id(alert_id, label="Alert"), populate_existing=True)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    old = a.status
    a.status = payload.status
    if payload.resolution_notes is not None:
        a.resolution_notes = payload.resolution_notes
    await log_activity(db, actor_id=current_user.id, action_type="war_room_updated", module="Surveys", reference_id=a.id,
                       description=f"War Room alert {format_id('WR', a.id)}: {old} → {payload.status}",
                       changes=[["status", old, payload.status]])
    await db.commit()
    a = await db.get(WarRoomAlert, a.id, populate_existing=True)
    return (await war_room_rows(db, [a]))[0]

