"""Birthdays page (frontend: Birthdays.jsx, VoterBirthdayDrawer.jsx, mockBirthdayApi).

    GET  /birthdays                         getVoters()   today's + next 7 days' birthdays (tab=today|upcoming)
    GET  /birthdays/summary                 cards: todayCount, upcomingCount, sentToday
    GET  /birthdays/settings                auto-wish settings
    PUT  /birthdays/settings                save settings
    POST /birthdays/run                     queue today's wishes now (call daily from a cron job at send_time)
    POST /birthdays/{epic}/retry            retrySend(epic)
    POST /birthdays/{epic}/mark-voted       markAsVoted(epic, party)   toggles voted
    POST /birthdays/{epic}/send-otp         sendOtp(epic)   -> {success, message}
    POST /birthdays/{epic}/verify-otp       {otp} -> marks the voter's mobile as verified

Wishes are queued in the message outbox (status Queued) until a WhatsApp /
SMS / voice provider is connected. Record shape follows mockBirthdayApi:
id, epic, name, relation, gender, dob, age, caste, religion, mobile,
masked_mobile, mandal, village, booth, party_member, status, send_by,
category, voted, voted_party, mapped, mobile_verified, survey_done,
survey_score, survey_leaning, internal_notes, birthday.
"""

import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, extract, or_, select

from app.core.config import settings as app_config
from app.core.dependencies import DbSession, page_access
from app.core.scope import resolve_scope
from app.models.engagement import BirthdayWish, MobileOtp, OutboxMessage
from app.models.settings import AppSettings
from app.models.voters import Voter
from app.services.activity_service import log_activity
from app.services.outbox_service import personalize, queue_message
from app.services.voter_profile import voter_rows
from app.services.voter_service import get_voter_or_404, set_polling_mark

router = APIRouter(prefix="/birthdays", tags=["Birthdays"])

CanView = page_access("voters", "view")
CanEdit = page_access("voters", "edit")

IST = timezone(timedelta(hours=5, minutes=30))
UPCOMING_DAYS = 7
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5

DEFAULT_SETTINGS: dict[str, Any] = {
    "send_automatically": True,
    "send_time": "10:00 AM",
    "channels": {"whatsapp": True, "sms": True, "voice_call": False},
    "language": "English + Telugu",
    "message_english": (
        "Happy birthday, {name} garu! Wishing you good health and a happy year ahead. "
        "– Inturi Nageswara Rao, MLA Kandukur"
    ),
    "message_telugu": (
        "{name} గారికి జన్మదిన శుభాకాంక్షలు! మీకు ఆయురారోగ్యాలు, సుఖసంతోషాలు కలగాలని కోరుకుంటున్నాను. "
        "– ఇంటూరి నాగేశ్వరరావు, కందుకూరు ఎమ్మెల్యే"
    ),
}

CHANNEL_LABEL = {"whatsapp": "WhatsApp", "sms": "SMS", "voice": "Voice call"}


class BirthdayChannels(BaseModel):
    whatsapp: bool = True
    sms: bool = True
    voice_call: bool = False


class BirthdaySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    send_automatically: bool = True
    send_time: str = "10:00 AM"
    channels: BirthdayChannels = BirthdayChannels()
    language: str = "English + Telugu"
    message_english: str = Field(default=DEFAULT_SETTINGS["message_english"], max_length=1000)
    message_telugu: str = Field(default=DEFAULT_SETTINGS["message_telugu"], max_length=1000)


class MarkVoted(BaseModel):
    party: str | None = None


class OtpVerify(BaseModel):
    otp: str = Field(min_length=4, max_length=8)


def today_ist() -> date:
    return datetime.now(IST).date()


def _birthday_in_year(dob: date, year: int) -> date:
    try:
        return dob.replace(year=year)
    except ValueError:  # 29 Feb in a non-leap year -> 28 Feb
        return date(year, 2, 28)


async def load_settings(db) -> tuple[AppSettings | None, dict[str, Any]]:
    row = (await db.execute(select(AppSettings).order_by(AppSettings.id).limit(1))).scalar_one_or_none()
    stored = (row.birthday_settings if row else None) or {}
    merged = {**DEFAULT_SETTINGS, **stored, "channels": {**DEFAULT_SETTINGS["channels"], **stored.get("channels", {})}}
    return row, merged


def preferred_channel(cfg: dict[str, Any]) -> str:
    ch = cfg["channels"]
    if ch.get("whatsapp"):
        return "whatsapp"
    if ch.get("sms"):
        return "sms"
    if ch.get("voice_call"):
        return "voice"
    return "whatsapp"


def wish_text(cfg: dict[str, Any], name: str) -> str:
    lang = (cfg.get("language") or "").lower()
    english = personalize(cfg["message_english"], name=name)
    telugu = personalize(cfg["message_telugu"], name=name)
    if "telugu" in lang and "english" in lang:
        return f"{english}\n\n{telugu}"
    return telugu if "telugu" in lang else english


async def birthday_voters(db, scope, start: date, days: int) -> list[Voter]:
    dates = [start + timedelta(days=i) for i in range(days + 1)]
    conditions = [
        and_(extract("month", Voter.dob) == d.month, extract("day", Voter.dob) == d.day) for d in dates
    ]
    if any(d.month == 2 and d.day == 28 for d in dates) and not _is_leap(start.year):
        conditions.append(and_(extract("month", Voter.dob) == 2, extract("day", Voter.dob) == 29))
    stmt = select(Voter).where(Voter.dob.is_not(None), Voter.removed_at.is_(None), or_(*conditions))
    stmt = scope.apply(stmt, mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)
    return list((await db.execute(stmt)).scalars().all())


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _mask(mobile: str | None) -> str | None:
    if not mobile or len(mobile) < 5:
        return mobile
    return f"{mobile[:2]}XXXXX{mobile[-3:]}"


async def birthday_rows(db, voters: list[Voter], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    today = today_ist()
    profiles = {r["id"]: r for r in await voter_rows(db, voters)}
    wish_dates = {v.id: _birthday_in_year(v.dob, today.year) for v in voters}
    wishes = {}
    if voters:
        stmt = (
            select(BirthdayWish, OutboxMessage.status)
            .outerjoin(OutboxMessage, OutboxMessage.id == BirthdayWish.outbox_id)
            .where(BirthdayWish.voter_id.in_([v.id for v in voters]))
        )
        for wish, outbox_status in (await db.execute(stmt)).all():
            if wish.wish_date == wish_dates.get(wish.voter_id):
                wishes[wish.voter_id] = (wish, outbox_status)
    out = []
    for v in voters:
        p = profiles[v.id]
        bday = wish_dates[v.id]
        if bday < today:  # birthday window crossing into next year
            bday = _birthday_in_year(v.dob, today.year + 1)
        wish, outbox_status = wishes.get(v.id, (None, None))
        status_value = outbox_status if outbox_status in ("Sent", "Delivered", "Read", "Failed") else (wish.status if wish else "Scheduled")
        if status_value in ("Delivered", "Read"):
            status_value = "Sent"
        channel = wish.channel if wish else preferred_channel(cfg)
        relation = " ".join(x for x in (v.relation_type or "", v.relation_name or "") if x).strip() or None
        out.append(
            {
                "id": v.id,
                "epic": v.epic_no,
                "name": v.name,
                "relation": relation,
                "gender": {"M": "Male", "F": "Female", "Third gender": "Other"}.get(p["gender"], p["gender"]),
                "dob": v.dob.isoformat(),
                "birthday": bday.isoformat(),
                "age": bday.year - v.dob.year,
                "caste": v.caste_category,
                "religion": v.religion,
                "mobile": v.mobile,
                "masked_mobile": _mask(v.mobile),
                "mandal": p["mandal"],
                "village": p["village"],
                "booth": p["booth_no"],
                "party_member": p.get("party_member") or "No",
                "status": status_value,
                "send_by": CHANNEL_LABEL.get(channel, channel),
                "category": "today" if bday == today else "upcoming",
                "voted": v.polling_status == "voted",
                "voted_party": v.voted_party,
                "mapped": p["mapped"],
                "mobile_verified": v.mobile_verified,
                "survey_done": p["survey_done"],
                "survey_score": p["survey_score"],
                "survey_leaning": p["survey_leaning"],
                "internal_notes": p["internal_notes"],
            }
        )
    out.sort(key=lambda r: (r["birthday"], r["name"]))
    return out


async def _queue_wish(db, voter: Voter, cfg: dict[str, Any]) -> BirthdayWish:
    today = today_ist()
    wish_date = _birthday_in_year(voter.dob, today.year)
    channel = preferred_channel(cfg)
    wish = (
        await db.execute(select(BirthdayWish).where(BirthdayWish.voter_id == voter.id, BirthdayWish.wish_date == wish_date))
    ).scalar_one_or_none()
    if wish is None:
        wish = BirthdayWish(voter_id=voter.id, wish_date=wish_date, channel=channel)
        db.add(wish)
        await db.flush()
    if not voter.mobile:
        wish.status = "Failed"
        return wish
    msg = queue_message(
        db, channel=channel, recipient=voter.mobile, recipient_name=voter.name,
        body=wish_text(cfg, voter.name), source="birthday", source_id=wish.id,
    )
    await db.flush()
    wish.outbox_id = msg.id
    wish.channel = channel
    wish.status = "Queued"
    return wish


@router.get("", summary="Birthdays today and in the next 7 days")
async def get_birthdays(
    db: DbSession,
    current_user: CanView,
    tab: str | None = Query(None, pattern="^(today|upcoming)$"),
) -> list[dict[str, Any]]:
    _, cfg = await load_settings(db)
    voters = await birthday_voters(db, await resolve_scope(db, current_user), today_ist(), UPCOMING_DAYS)
    rows = await birthday_rows(db, voters, cfg)
    return [r for r in rows if tab is None or r["category"] == tab]


@router.get("/summary", summary="Birthdays page cards")
async def birthday_summary(db: DbSession, current_user: CanView) -> dict[str, int]:
    _, cfg = await load_settings(db)
    rows = await birthday_rows(db, await birthday_voters(db, await resolve_scope(db, current_user), today_ist(), UPCOMING_DAYS), cfg)
    return {
        "todayCount": sum(1 for r in rows if r["category"] == "today"),
        "upcomingCount": sum(1 for r in rows if r["category"] == "upcoming"),
        "sentToday": sum(1 for r in rows if r["category"] == "today" and r["status"] == "Sent"),
        "queuedToday": sum(1 for r in rows if r["category"] == "today" and r["status"] == "Queued"),
    }


@router.get("/settings", summary="Birthday auto-wish settings")
async def get_birthday_settings(db: DbSession, current_user: CanView) -> dict[str, Any]:
    return (await load_settings(db))[1]


@router.put("/settings", summary="Save birthday auto-wish settings")
async def save_birthday_settings(payload: BirthdaySettings, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    row, _ = await load_settings(db)
    if row is None:
        row = AppSettings()
        db.add(row)
    row.birthday_settings = payload.model_dump()
    await log_activity(db, actor_id=current_user.id, action_type="birthday_settings_updated", module="Birthdays",
                       reference_id=None, description="Updated birthday wish settings")
    await db.commit()
    return (await load_settings(db))[1]


@router.post("/run", summary="Queue today's birthday wishes (for a daily cron job)")
async def run_birthday_wishes(db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    _, cfg = await load_settings(db)
    if not cfg["send_automatically"]:
        return {"queued": 0, "skipped": "send_automatically is off"}
    today = today_ist()
    voters = await birthday_voters(db, await resolve_scope(db, current_user), today, 0)
    queued = failed = 0
    for v in voters:
        existing = (
            await db.execute(select(BirthdayWish).where(BirthdayWish.voter_id == v.id,
                                                        BirthdayWish.wish_date == _birthday_in_year(v.dob, today.year)))
        ).scalar_one_or_none()
        if existing and existing.status in ("Queued", "Sent"):
            continue
        wish = await _queue_wish(db, v, cfg)
        if wish.status == "Failed":
            failed += 1
        else:
            queued += 1
    await db.commit()
    return {"queued": queued, "failed_no_mobile": failed}


@router.post("/{epic}/retry", summary="Retry sending a birthday wish")
async def retry_wish(epic: str, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    voter = await get_voter_or_404(db, epic, include_removed=False)
    if voter.dob is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This voter has no date of birth")
    _, cfg = await load_settings(db)
    wish = await _queue_wish(db, voter, cfg)
    if wish.status == "Failed":
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This voter has no mobile number")
    await db.commit()
    return (await birthday_rows(db, [voter], cfg))[0]


@router.post("/{epic}/mark-voted", summary="Toggle voted for a birthday voter")
async def mark_voted(epic: str, db: DbSession, current_user: CanEdit, payload: MarkVoted | None = None) -> dict[str, Any]:
    voter = await get_voter_or_404(db, epic, include_removed=False)
    set_polling_mark(
        voter,
        voted=voter.polling_status != "voted",
        party=payload.party if payload else None,
        marked_by=current_user.name,
    )
    await db.commit()
    await db.refresh(voter)
    _, cfg = await load_settings(db)
    return (await birthday_rows(db, [voter], cfg))[0] if voter.dob else {"success": True}


def _hash_otp(voter_id: int, code: str) -> str:
    return hmac.new(app_config.secret_key.encode(), f"{voter_id}:{code}".encode(), hashlib.sha256).hexdigest()


@router.post("/{epic}/send-otp", summary="Send a mobile-verification OTP to the voter")
async def send_otp(epic: str, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    voter = await get_voter_or_404(db, epic, include_removed=False)
    if not voter.mobile:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This voter has no mobile number")
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = MobileOtp(
        voter_id=voter.id, mobile=voter.mobile, code_hash=_hash_otp(voter.id, code),
        expires_at=datetime.now(timezone.utc) + OTP_TTL,
    )
    db.add(otp)
    await db.flush()
    queue_message(
        db, channel="sms", recipient=voter.mobile, recipient_name=voter.name,
        body=f"Your verification code for MLA Kandukur office is {code}. Valid for 10 minutes.",
        source="otp", source_id=otp.id,
    )
    await db.commit()
    return {"success": True, "message": "OTP sent successfully"}


@router.post("/{epic}/verify-otp", summary="Verify the OTP and mark the mobile as verified")
async def verify_otp(epic: str, payload: OtpVerify, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    voter = await get_voter_or_404(db, epic, include_removed=False)
    otp = (
        await db.execute(
            select(MobileOtp).where(MobileOtp.voter_id == voter.id, MobileOtp.verified_at.is_(None))
            .order_by(MobileOtp.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if otp is None or otp.expires_at < now or otp.attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP expired. Send a new one.")
    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _hash_otp(voter.id, payload.otp.strip())):
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect OTP")
    otp.verified_at = now
    voter.mobile_verified = voter.mobile == otp.mobile
    await log_activity(db, actor_id=current_user.id, action_type="mobile_verified", module="voters", reference_id=voter.id,
                       description=f"Verified mobile for {voter.epic_no}")
    await db.commit()
    return {"success": True, "mobile_verified": voter.mobile_verified}

