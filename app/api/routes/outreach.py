"""Communication pages, part 2.

Broadcast lists (WhatsappBroadcast.jsx, mockBroadcastApi)
    GET /whatsapp/broadcast-lists | GET /whatsapp/broadcast-lists/groups | POST | GET,DELETE /{id}
Chat history (WhatsappChatHistory.jsx, mockChatHistoryApi)
    GET  /whatsapp/chats                       getChats()
    POST /whatsapp/chats/{chatId}/messages     sendMessage(chatId, text)
    POST /whatsapp/chats/{chatId}/read         mark a chat as read
    POST /whatsapp/webhook                     inbound messages from the WhatsApp provider (X-Webhook-Token);
                                               active auto-replies answer matching keywords
Social media posts (SocialMediaPosts.jsx)        GET, POST /social-posts | PATCH, DELETE /social-posts/{id}
Auto replies (AutoReplies.jsx)                   GET, POST /auto-replies | PATCH /{id}/toggle | DELETE /{id}
Calling to voters (CallingToVoters.jsx)          GET /voter-calls/summary | /voter-calls/staff | /voter-calls/lookup/{epic}
                                                 GET, POST /voter-calls | GET /voter-calls/export
Team meetings (TeamMeetings.jsx)                 GET /team-meetings?status=upcoming|past | POST
                                                 POST /{id}/cancel | POST /{id}/complete | DELETE /{id}
"""

import csv
import io
import re
import datetime as dt
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.models.communication import AutoReply, BroadcastList, ChatMessage, SocialPost, TeamMeeting, VoterCall
from app.models.geography import Mandal, Village
from app.models.staff import StaffUser
from app.models.voters import Voter
from app.services.activity_service import log_activity
from app.services.campaign_service import IST, list_groups
from app.services.outbox_service import queue_message

CanView = page_access("communication", "view")
CanEdit = page_access("communication", "edit")
CanDelete = page_access("communication", "admin")
CanDownload = page_access("communication", "download")

broadcast_router = APIRouter(prefix="/whatsapp/broadcast-lists", tags=["Communication - WhatsApp"])
chat_router = APIRouter(prefix="/whatsapp", tags=["Communication - WhatsApp"])
social_router = APIRouter(prefix="/social-posts", tags=["Communication - Social"])
auto_reply_router = APIRouter(prefix="/auto-replies", tags=["Communication - Auto replies"])
calls_router = APIRouter(prefix="/voter-calls", tags=["Communication - Calling to voters"])
meetings_router = APIRouter(prefix="/team-meetings", tags=["Communication - Team meetings"])

MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def _clock(value: datetime | None) -> str | None:
    if value is None:
        return None
    local = value.astimezone(IST)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{local.strftime('%M')} {local.strftime('%p')}"


def _relative(value: datetime | None) -> str | None:
    if value is None:
        return None
    delta = datetime.now(timezone.utc) - value
    if delta < timedelta(minutes=2):
        return "Just now"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)} min ago"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)} h ago"
    return value.astimezone(IST).strftime("%d %b %Y")


# --- broadcast lists -----------------------------------------------------------------


class Contact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    mobile: str
    village: str | None = None

    @field_validator("mobile", mode="before")
    @classmethod
    def _mobile(cls, v: object) -> str:
        digits = re.sub(r"\D", "", str(v or ""))[-10:]
        if not MOBILE_RE.match(digits):
            raise ValueError(f"invalid mobile number '{v}'")
        return digits


class BroadcastListForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    made_from: str | None = "Manual entry"
    contacts: list[Contact] = []


def list_row(bl: BroadcastList, include_contacts: bool = True) -> dict[str, Any]:
    row = {
        "id": format_id("BL", bl.id),
        "name": bl.name,
        "contacts_count": len(bl.contacts or []),
        "made_from": bl.made_from,
        "updated": _relative(bl.updated_at or bl.created_at),
    }
    if include_contacts:
        row["contacts"] = bl.contacts or []
    return row


@broadcast_router.get("", summary="getLists()")
async def get_lists(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    rows = (await db.execute(select(BroadcastList).order_by(BroadcastList.id.desc()))).scalars().all()
    return [list_row(bl) for bl in rows]


@broadcast_router.get("/groups", summary="getGroups() — groups a list can be built from")
async def broadcast_groups(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    return await list_groups(db, include_lists=False)


@broadcast_router.post("", status_code=status.HTTP_201_CREATED, summary="createList(payload)")
async def create_list(payload: BroadcastListForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    seen, contacts = set(), []
    for c in payload.contacts:
        if c.mobile not in seen:
            seen.add(c.mobile)
            contacts.append(c.model_dump())
    bl = BroadcastList(name=payload.name, made_from=payload.made_from, contacts=contacts, created_by=current_user.id)
    db.add(bl)
    await db.commit()
    await db.refresh(bl)
    return list_row(bl)


@broadcast_router.get("/{list_id}", summary="One list with contacts")
async def get_list(list_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    bl = await db.get(BroadcastList, parse_id(list_id, label="List"))
    if bl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return list_row(bl)


@broadcast_router.delete("/{list_id}", summary="deleteList(id)")
async def delete_list(list_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    bl = await db.get(BroadcastList, parse_id(list_id, label="List"))
    if bl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    await db.delete(bl)
    await db.commit()
    return {"success": True}


# --- chat history ------------------------------------------------------------------------


class ChatReply(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class InboundMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mobile: str = Field(validation_alias=AliasChoices("mobile", "from", "phone"))
    text: str = Field(validation_alias=AliasChoices("text", "message", "body"))
    name: str | None = None


def _chat_id(mobile: str) -> str:
    return f"CHAT-{mobile}"


def _mobile_from_chat(chat_id: str) -> str:
    digits = re.sub(r"\D", "", chat_id)
    if not digits:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return digits


async def _voter_names(db, mobiles: list[str]) -> dict[str, tuple[str, str | None]]:
    if not mobiles:
        return {}
    stmt = (
        select(Voter.mobile, Voter.name, Village.name)
        .join(Village, Village.id == Voter.village_id)
        .where(Voter.mobile.in_(mobiles))
    )
    return {m: (n, v) for m, n, v in (await db.execute(stmt)).all()}


@chat_router.get("/chats", summary="getChats() — one chat per mobile, newest first")
async def get_chats(db: DbSession, current_user: CanView, limit: int = Query(200, ge=1, le=1000),
                    messages_per_chat: int = Query(100, ge=1, le=1000)) -> list[dict[str, Any]]:
    latest = (
        select(ChatMessage.mobile, func.max(ChatMessage.created_at).label("last"))
        .group_by(ChatMessage.mobile).order_by(func.max(ChatMessage.created_at).desc()).limit(limit)
    )
    mobiles = [m for m, _ in (await db.execute(latest)).all()]
    if not mobiles:
        return []
    msgs = (
        await db.execute(select(ChatMessage).where(ChatMessage.mobile.in_(mobiles)).order_by(ChatMessage.created_at))
    ).scalars().all()
    known = await _voter_names(db, mobiles)
    by_mobile: dict[str, list[ChatMessage]] = {}
    for m in msgs:
        by_mobile.setdefault(m.mobile, []).append(m)
    out = []
    for mobile in mobiles:
        items = by_mobile.get(mobile, [])[-messages_per_chat:]
        name = next((m.contact_name for m in reversed(items) if m.contact_name), None)
        voter_name, village = known.get(mobile, (None, None))
        last = items[-1] if items else None
        out.append({
            "id": _chat_id(mobile),
            "name": name or voter_name or mobile,
            "mobile": mobile,
            "village": village,
            "lastMessage": last.text if last else "",
            "lastTime": _clock(last.created_at) if last else None,
            "unread": sum(1 for m in items if m.direction == "in" and m.read_at is None),
            "messages": [
                {"id": format_id("MSG", m.id), "sender": "agent" if m.direction == "out" else "user", "text": m.text,
                 "time": _clock(m.created_at)}
                for m in items
            ],
        })
    return out


@chat_router.post("/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED, summary="sendMessage(chatId, text)")
async def send_chat_message(chat_id: str, payload: ChatReply, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    mobile = _mobile_from_chat(chat_id)
    msg = ChatMessage(mobile=mobile, direction="out", text=payload.text, sent_by=current_user.id,
                      read_at=datetime.now(timezone.utc))
    db.add(msg)
    queue_message(db, channel="whatsapp", recipient=mobile, body=payload.text, source="chat")
    await db.commit()
    await db.refresh(msg)
    return {"id": format_id("MSG", msg.id), "sender": "agent", "text": msg.text, "time": _clock(msg.created_at)}


@chat_router.post("/chats/{chat_id}/read", summary="Mark a chat's incoming messages as read")
async def mark_chat_read(chat_id: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    mobile = _mobile_from_chat(chat_id)
    unread = (
        await db.execute(select(ChatMessage).where(ChatMessage.mobile == mobile, ChatMessage.direction == "in",
                                                   ChatMessage.read_at.is_(None)))
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for m in unread:
        m.read_at = now
    await db.commit()
    return {"success": True, "marked": len(unread)}


@chat_router.post("/webhook", summary="Inbound WhatsApp message (called by the WhatsApp provider)")
async def whatsapp_webhook(
    payload: InboundMessage, db: DbSession, x_webhook_token: str | None = Header(None)
) -> dict[str, Any]:
    expected = settings.whatsapp_webhook_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "WhatsApp webhook is not configured")
    if x_webhook_token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook token")
    mobile = re.sub(r"\D", "", payload.mobile)[-10:]
    db.add(ChatMessage(mobile=mobile, contact_name=payload.name, direction="in", text=payload.text))
    replied = None
    text = payload.text.strip().lower()
    rules = (await db.execute(select(AutoReply).where(AutoReply.is_active.is_(True), AutoReply.channel == "WhatsApp"))).scalars().all()
    for rule in rules:
        if rule.keyword.strip().lower() and rule.keyword.strip().lower() in text:
            rule.times_used += 1
            db.add(ChatMessage(mobile=mobile, direction="out", text=rule.reply, read_at=datetime.now(timezone.utc)))
            queue_message(db, channel="whatsapp", recipient=mobile, body=rule.reply, source="auto_reply", source_id=rule.id)
            replied = format_id("AR", rule.id)
            break
    await db.commit()
    return {"success": True, "auto_reply": replied}


# --- social media posts ---------------------------------------------------------------------


class SocialPostForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channels: list[str] = Field(min_length=1)
    postText: str = Field(min_length=1)
    link: str | None = None
    whenMode: str = "now"
    dateTime: str | None = None
    surveyId: str | None = None


class SocialPostUpdate(BaseModel):
    status_type: str = Field(pattern="^(scheduled|posted|reminder|failed|cancelled)$")


STATUS_LABELS = {
    "reminder": "Reminder · post by hand",
    "scheduled": "Scheduled",
    "posted": "Posted",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


def _parse_when(value: str | None) -> datetime | None:
    """Accepts "2026-10-24, 09:30", "2026-10-24T09:30" or an ISO datetime (IST)."""
    if not value:
        return None
    cleaned = value.replace(", ", "T").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def _fmt_post(value: datetime | None) -> str | None:
    if value is None:
        return None
    local = value.astimezone(IST)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%d %b %Y')}, {hour}:{local.strftime('%M')} {local.strftime('%p').lower()}"


def post_row(p: SocialPost) -> dict[str, Any]:
    when = p.scheduled_for or p.created_at
    return {
        "id": format_id("SMP", p.id),
        "date_time": _fmt_post(when),
        "done_time": f"done {_fmt_post(p.done_at)}" if p.done_at else "Pending",
        "channel": p.channel,
        "post_text": p.post_text,
        "link": p.link or "",
        "survey_id": p.survey_id,
        "status": STATUS_LABELS.get(p.status_type, p.status_type),
        "status_type": p.status_type,
    }


@social_router.get("", summary="getPosts()")
async def get_posts(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    rows = (await db.execute(select(SocialPost).order_by(SocialPost.id.desc()))).scalars().all()
    return [post_row(p) for p in rows]


@social_router.post("", status_code=status.HTTP_201_CREATED, summary="createPost(payload) — one post per channel")
async def create_post(payload: SocialPostForm, db: DbSession, current_user: CanEdit) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    when = None if payload.whenMode == "now" else _parse_when(payload.dateTime)
    survey_id = payload.surveyId
    if not survey_id and payload.link:
        m = re.search(r"(SV-\d+)", payload.link)
        survey_id = m.group(1) if m else None
    posts = []
    for channel in payload.channels:
        # No social network APIs are connected: "now" posts are reminders to post by hand.
        p = SocialPost(
            channel=channel, post_text=payload.postText, link=payload.link, survey_id=survey_id,
            scheduled_for=when, status_type="scheduled" if when and when > now else "reminder", created_by=current_user.id,
        )
        db.add(p)
        posts.append(p)
    await db.commit()
    for p in posts:
        await db.refresh(p)
    return [post_row(p) for p in posts]


@social_router.patch("/{post_id}", summary="Mark a post as posted / failed / cancelled")
async def update_post(post_id: str, payload: SocialPostUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    p = await db.get(SocialPost, parse_id(post_id, label="Post"))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    p.status_type = payload.status_type
    p.done_at = datetime.now(timezone.utc) if payload.status_type == "posted" else p.done_at
    await db.commit()
    await db.refresh(p)
    return post_row(p)


@social_router.delete("/{post_id}", summary="deletePost(id)")
async def delete_post(post_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    p = await db.get(SocialPost, parse_id(post_id, label="Post"))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    await db.delete(p)
    await db.commit()
    return {"success": True}


# --- auto replies -------------------------------------------------------------------------------


class AutoReplyForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    keyword: str = Field(min_length=1, max_length=100)
    channel: str = "WhatsApp"
    reply: str = Field(min_length=1)
    isActive: bool = Field(default=True, validation_alias=AliasChoices("isActive", "is_active"))


def reply_row(r: AutoReply) -> dict[str, Any]:
    return {"id": format_id("AR", r.id), "keyword": r.keyword, "channel": r.channel, "reply": r.reply,
            "is_active": r.is_active, "times_used": r.times_used}


@auto_reply_router.get("", summary="getReplies()")
async def get_replies(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    return [reply_row(r) for r in (await db.execute(select(AutoReply).order_by(AutoReply.id.desc()))).scalars().all()]


@auto_reply_router.post("", status_code=status.HTTP_201_CREATED, summary="addReply(payload)")
async def add_reply(payload: AutoReplyForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    clash = (
        await db.execute(select(AutoReply.id).where(func.lower(AutoReply.keyword) == payload.keyword.strip().lower(),
                                                    AutoReply.channel == payload.channel))
    ).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, f"An auto reply for '{payload.keyword}' already exists")
    r = AutoReply(keyword=payload.keyword.strip(), channel=payload.channel, reply=payload.reply,
                  is_active=payload.isActive, created_by=current_user.id)
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return reply_row(r)


@auto_reply_router.patch("/{reply_id}/toggle", summary="toggleReplyStatus(id)")
async def toggle_reply(reply_id: str, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    r = await db.get(AutoReply, parse_id(reply_id, label="Reply"))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")
    r.is_active = not r.is_active
    await db.commit()
    await db.refresh(r)
    return reply_row(r)


@auto_reply_router.delete("/{reply_id}", summary="deleteReply(id)")
async def delete_reply(reply_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    r = await db.get(AutoReply, parse_id(reply_id, label="Reply"))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")
    await db.delete(r)
    await db.commit()
    return {"success": True}


# --- calling to voters -----------------------------------------------------------------------------

OUTCOMES = ("Answered", "Not answered", "Busy", "Switched off", "Wrong number", "Call back later")


class CallForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    epicNo: str | None = Field(default=None, validation_alias=AliasChoices("epicNo", "epic_no"))
    name: str = Field(default="Unlisted Voter", max_length=150)
    mobile: str
    village: str | None = None
    outcome: str
    notes: str | None = None

    @field_validator("mobile", mode="before")
    @classmethod
    def _mobile(cls, v: object) -> str:
        digits = re.sub(r"\D", "", str(v or ""))[-10:]
        if len(digits) != 10:
            raise ValueError("mobile must be 10 digits")
        return digits

    @field_validator("outcome")
    @classmethod
    def _outcome(cls, v: str) -> str:
        if v not in OUTCOMES:
            raise ValueError(f"outcome must be one of: {', '.join(OUTCOMES)}")
        return v


def call_row(c: VoterCall) -> dict[str, Any]:
    local = c.created_at.astimezone(IST)
    return {
        "id": format_id("VC", c.id),
        "when": _clock(c.created_at),
        "date": local.strftime("%d %b"),
        "epic_no": c.epic_no or "—",
        "person_name": c.person_name,
        "mobile": c.mobile,
        "village": c.village or "—",
        "outcome": c.outcome,
        "notes": c.notes or "—",
        "logged_by": c.logged_by_name,
        "created_at": c.created_at,
    }


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, IST)
    return start, start + timedelta(days=1)


@calls_router.get("/summary", summary="getSummary() — today's calls")
async def calls_summary(db: DbSession, current_user: CanView) -> dict[str, int]:
    start, end = _day_bounds(datetime.now(IST).date())
    today = select(VoterCall).where(VoterCall.created_at >= start, VoterCall.created_at < end).subquery()
    calls, staff, answered = (
        await db.execute(select(func.count(), func.count(func.distinct(today.c.logged_by)),
                                func.count().filter(today.c.outcome == "Answered")).select_from(today))
    ).one()
    callback = (await db.execute(select(func.count()).select_from(VoterCall).where(VoterCall.outcome == "Call back later"))).scalar_one()
    return {"callsToday": calls, "staffCount": staff, "answeredToday": answered, "toCallBack": callback}


@calls_router.get("/staff", summary="Staff names for the 'logged by' filter")
async def call_staff(db: DbSession, current_user: CanView) -> list[str]:
    names = (await db.execute(select(StaffUser.name).where(StaffUser.status == "active").order_by(StaffUser.name))).scalars().all()
    return ["All staff", *names]


@calls_router.get("/lookup/{epic_no}", summary="lookupVoterByEpic(epic)")
async def call_lookup(epic_no: str, db: DbSession, current_user: CanView) -> dict[str, Any]:
    row = (
        await db.execute(
            select(Voter, Village.name, Mandal.name).join(Village, Village.id == Voter.village_id)
            .join(Mandal, Mandal.id == Voter.mandal_id)
            .where(Voter.epic_no == epic_no.strip().upper(), Voter.removed_at.is_(None))
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voter not found")
    v, village, mandal = row
    return {"epic_no": v.epic_no, "name": v.name, "mobile": v.mobile, "village": village, "mandal": mandal}


async def _calls(db, *, day: date | None, staff: str | None, outcome: str | None, q: str | None, limit: int | None):
    stmt = select(VoterCall)
    if day:
        start, end = _day_bounds(day)
        stmt = stmt.where(VoterCall.created_at >= start, VoterCall.created_at < end)
    if staff and staff != "All staff":
        stmt = stmt.where(VoterCall.logged_by_name == staff)
    if outcome:
        stmt = stmt.where(VoterCall.outcome == outcome)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(VoterCall.person_name.ilike(term), VoterCall.mobile.ilike(term), VoterCall.epic_no.ilike(term)))
    stmt = stmt.order_by(VoterCall.id.desc())
    if limit:
        stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@calls_router.get("", summary="getCalls(filters)")
async def get_calls(
    db: DbSession,
    current_user: CanView,
    day: date | None = Query(None, alias="date"),
    staff: str | None = Query(None),
    outcome: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
) -> list[dict[str, Any]]:
    return [call_row(c) for c in await _calls(db, day=day, staff=staff, outcome=outcome, q=q, limit=limit)]


@calls_router.post("", status_code=status.HTTP_201_CREATED, summary="logCall(payload)")
async def log_call(payload: CallForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    voter = None
    if payload.epicNo:
        voter = (await db.execute(select(Voter).where(Voter.epic_no == payload.epicNo.strip().upper()))).scalar_one_or_none()
    village = payload.village
    if voter and not village:
        village = (await db.execute(select(Village.name).where(Village.id == voter.village_id))).scalar_one_or_none()
    c = VoterCall(
        voter_id=voter.id if voter else None, epic_no=payload.epicNo.strip().upper() if payload.epicNo else None,
        person_name=payload.name.strip() or (voter.name if voter else "Unlisted Voter"), mobile=payload.mobile,
        village=village, outcome=payload.outcome, notes=payload.notes, logged_by=current_user.id,
        logged_by_name=current_user.name,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return call_row(c)


@calls_router.get("/export", summary="exportCallsCsv()", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
async def export_calls(
    db: DbSession,
    current_user: CanDownload,
    day: date | None = Query(None, alias="date"),
    staff: str | None = Query(None),
    outcome: str | None = Query(None),
) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["When", "Date", "EPIC", "Person", "Mobile", "Village", "Outcome", "Notes", "By"])
    for c in await _calls(db, day=day, staff=staff, outcome=outcome, q=None, limit=None):
        r = call_row(c)
        w.writerow([r["when"], r["date"], r["epic_no"], r["person_name"], r["mobile"], r["village"], r["outcome"],
                    r["notes"], r["logged_by"]])
    return Response(content=("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="voter_calls.csv"'})


# --- team meetings -------------------------------------------------------------------------------------


class MeetingForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="Team Review Meeting", min_length=1, max_length=200)
    date: dt.date
    time: dt.time | None = None
    linkOrVenue: str | None = Field(default=None, validation_alias=AliasChoices("linkOrVenue", "link_or_venue"))
    participants: str | None = "Coordinators & Booth Agents"
    notes: str | None = None


def meeting_row(m: TeamMeeting) -> dict[str, Any]:
    return {
        "id": format_id("MTG", m.id),
        "title": m.title,
        "date": m.meeting_date.isoformat(),
        "time": m.meeting_time.strftime("%H:%M") if m.meeting_time else None,
        "link_or_venue": m.link_or_venue,
        "participants": m.participants,
        "notes": m.notes or "",
        "status": m.status,
    }


async def _close_past_meetings(db) -> None:
    """Upcoming meetings whose date has passed become Completed."""
    today = datetime.now(IST).date()
    stale = (
        await db.execute(select(TeamMeeting).where(TeamMeeting.status == "Upcoming", TeamMeeting.meeting_date < today))
    ).scalars().all()
    for m in stale:
        m.status = "Completed"
    if stale:
        await db.commit()


@meetings_router.get("", summary="getMeetings(status) — upcoming or past")
async def get_meetings(
    db: DbSession, current_user: CanView, status_filter: str = Query("upcoming", alias="status", pattern="^(upcoming|past|all)$")
) -> list[dict[str, Any]]:
    await _close_past_meetings(db)
    stmt = select(TeamMeeting)
    if status_filter == "upcoming":
        stmt = stmt.where(TeamMeeting.status == "Upcoming").order_by(TeamMeeting.meeting_date, TeamMeeting.meeting_time)
    elif status_filter == "past":
        stmt = stmt.where(TeamMeeting.status != "Upcoming").order_by(TeamMeeting.meeting_date.desc())
    else:
        stmt = stmt.order_by(TeamMeeting.meeting_date.desc())
    return [meeting_row(m) for m in (await db.execute(stmt)).scalars().all()]


@meetings_router.post("", status_code=status.HTTP_201_CREATED, summary="planMeeting(payload)")
async def plan_meeting(payload: MeetingForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    if payload.date < datetime.now(IST).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Meeting date is in the past")
    m = TeamMeeting(title=payload.title, meeting_date=payload.date, meeting_time=payload.time,
                    link_or_venue=payload.linkOrVenue, participants=payload.participants, notes=payload.notes,
                    created_by=current_user.id)
    db.add(m)
    await db.flush()
    await log_activity(db, actor_id=current_user.id, action_type="meeting_planned", module="Communication",
                       reference_id=m.id, description=f"Planned meeting {m.title} on {m.meeting_date}")
    await db.commit()
    await db.refresh(m)
    return meeting_row(m)


async def _meeting(db, meeting_id: str) -> TeamMeeting:
    m = await db.get(TeamMeeting, parse_id(meeting_id, label="Meeting"))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")
    return m


@meetings_router.post("/{meeting_id}/cancel", summary="cancelMeeting(id)")
async def cancel_meeting(meeting_id: str, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    m = await _meeting(db, meeting_id)
    m.status = "Cancelled"
    await db.commit()
    await db.refresh(m)
    return meeting_row(m)


@meetings_router.post("/{meeting_id}/complete", summary="Mark a meeting as completed")
async def complete_meeting(meeting_id: str, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    m = await _meeting(db, meeting_id)
    m.status = "Completed"
    await db.commit()
    await db.refresh(m)
    return meeting_row(m)


@meetings_router.delete("/{meeting_id}", summary="Delete a meeting")
async def delete_meeting(meeting_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    await db.delete(await _meeting(db, meeting_id))
    await db.commit()
    return {"success": True}


ROUTERS = [broadcast_router, chat_router, social_router, auto_reply_router, calls_router, meetings_router]
