"""Communication pages: dashboard, analytics, WhatsApp / SMS / email sends, templates, push, AI calling.

Communication dashboard (CommunicationDashboard.js, mockCommunicationApi)
    GET    /communication/dashboard              getDashboardData()
    POST   /communication/campaigns              createCampaign {name, channel, recipients, message}
    DELETE /communication/campaigns/{id}
    GET    /communication/groups                 recipient groups with reachable counts
    POST   /communication/recipients             {groupIds} -> {total, recipients[]} (preview, first 500)
Campaign analytics (CampaignAnalytics.jsx)
    GET    /campaign-analytics                   ?from_date&to_date&channel
    GET    /campaign-analytics/export            CSV
WhatsApp (SendWhatsAppMessage.jsx, WhatsappTemplates.jsx)
    GET    /whatsapp/groups | POST /whatsapp/recipients | POST /whatsapp/test | GET,POST /whatsapp/campaigns
    GET,POST /message-templates?channel=WhatsApp|Email|SMS | PUT,DELETE /message-templates/{id}
Email (EmailCampaigns.jsx, EmailTemplates.jsx)
    GET,POST /email/campaigns       (templates: /message-templates?channel=Email)
SMS (SMSCampaigns.jsx)
    GET /sms/groups | GET,POST /sms/dlt-templates | DELETE /sms/dlt-templates/{id} | GET,POST /sms/campaigns
Push (PushNotifications.jsx)
    GET,POST /push-notifications
AI calling agent (AiCallingAgent.jsx)
    GET /ai-calling/groups | GET,POST /ai-calling/campaigns | DELETE /ai-calling/campaigns/{id}

Nothing is sent to a real provider yet: every message is queued in message_outbox.
"""

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.models.communication import CommCampaign, MessageTemplate
from app.models.engagement import OutboxMessage
from app.services.activity_service import log_activity
from app.services.campaign_service import (
    CHANNEL_LABEL,
    IST,
    campaign_row,
    campaign_stats,
    create_campaign,
    fmt_dt,
    list_groups,
    parse_schedule,
    resolve_recipients,
)
from app.services.outbox_service import normalize_channel, queue_message

CanView = page_access("communication", "view")
CanEdit = page_access("communication", "edit")
CanDelete = page_access("communication", "admin")
CanDownload = page_access("communication", "download")

comm_router = APIRouter(prefix="/communication", tags=["Communication"])
analytics_router = APIRouter(prefix="/campaign-analytics", tags=["Communication"])
whatsapp_router = APIRouter(prefix="/whatsapp", tags=["Communication - WhatsApp"])
templates_router = APIRouter(prefix="/message-templates", tags=["Communication - Templates"])
email_router = APIRouter(prefix="/email", tags=["Communication - Email"])
sms_router = APIRouter(prefix="/sms", tags=["Communication - SMS"])
push_router = APIRouter(prefix="/push-notifications", tags=["Communication - Push"])
ai_router = APIRouter(prefix="/ai-calling", tags=["Communication - AI Calling"])

MESSAGE_CHANNELS = ("whatsapp", "sms", "email")


# --- shared helpers -----------------------------------------------------------------


async def _campaigns(db, channel: str | None = None, *, since: datetime | None = None, until: datetime | None = None,
                     limit: int | None = None) -> list[CommCampaign]:
    stmt = select(CommCampaign)
    if channel:
        stmt = stmt.where(CommCampaign.channel == channel)
    if since:
        stmt = stmt.where(CommCampaign.created_at >= since)
    if until:
        stmt = stmt.where(CommCampaign.created_at < until)
    stmt = stmt.order_by(CommCampaign.id.desc())
    if limit:
        stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def _rows(db, campaigns: list[CommCampaign]) -> list[dict[str, Any]]:
    stats = await campaign_stats(db, [c.id for c in campaigns])
    return [campaign_row(c, stats.get(c.id)) for c in campaigns]


async def _get_campaign(db, campaign_id: str, channel: str | None = None) -> CommCampaign:
    c = await db.get(CommCampaign, parse_id(campaign_id, label="Campaign"))
    if c is None or (channel and c.channel != channel):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return c


async def _delete_campaign(db, c: CommCampaign, user) -> None:
    """Deleting a campaign cancels its messages that haven't gone out yet."""
    pending = (
        await db.execute(
            select(OutboxMessage).where(
                OutboxMessage.source == "campaign", OutboxMessage.source_id == c.id,
                OutboxMessage.status.in_(("Queued", "Scheduled")),
            )
        )
    ).scalars().all()
    for m in pending:
        m.status = "Cancelled"
    await log_activity(db, actor_id=user.id, action_type="campaign_deleted", module="Communication", reference_id=c.id,
                       description=f"Deleted {CHANNEL_LABEL.get(c.channel, c.channel)} campaign {c.name}")
    await db.delete(c)
    await db.commit()


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recipients = sum(r["total"] for r in rows)
    sent = sum(r["sent"] for r in rows)
    delivered = sum(r["delivered"] for r in rows)
    read = sum(r["read"] for r in rows)
    failed = sum(r["failed"] for r in rows)
    return {
        "campaigns": len(rows),
        "scheduled": sum(1 for r in rows if r["status"] == "Scheduled"),
        "recipients": recipients,
        "messages_sent": sent,
        "queued": sum(r["queued"] for r in rows),
        "delivered_pct": f"{round(delivered * 100 / sent)}%" if sent else "—",
        "delivered_count": delivered,
        "read_pct": f"{round(read * 100 / delivered)}%" if delivered else "—",
        "read_count": read,
        "failed": failed,
        "failed_desc": "wrong or inactive numbers" if failed else "—",
    }


# --- communication dashboard -----------------------------------------------------------


class QuickCampaign(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    channel: str = "WhatsApp"
    recipients: int = Field(default=0, ge=0)
    message: str | None = None
    groupIds: list[str] | None = None


class RecipientsRequest(BaseModel):
    groupIds: list[str] = Field(default_factory=list, validation_alias=AliasChoices("groupIds", "group_ids", "selectedGroupIds"))


@comm_router.get("/dashboard", summary="Communication dashboard data")
async def dashboard(db: DbSession, current_user: CanView) -> dict[str, Any]:
    rows = await _rows(db, await _campaigns(db))
    by_channel = {ch: sum(r["total"] for r in rows if r["channel"] == CHANNEL_LABEL[ch]) for ch in MESSAGE_CHANNELS}
    per_channel = {
        ch: {"sent": sum(r["sent"] for r in rows if r["channel"] == CHANNEL_LABEL[ch]),
             "queued": sum(r["queued"] for r in rows if r["channel"] == CHANNEL_LABEL[ch]),
             "campaigns": sum(1 for r in rows if r["channel"] == CHANNEL_LABEL[ch])}
        for ch in MESSAGE_CHANNELS
    }
    today = datetime.now(IST).date()
    weeks = [today - timedelta(days=7 * i) for i in range(5, -1, -1)]
    trend = []
    for start in weeks:
        end = start + timedelta(days=7)
        point = {"label": start.strftime("%d %b"), "date": start.isoformat()}
        for ch in MESSAGE_CHANNELS:
            point[ch] = sum(
                r["total"] for r in rows
                if r["channel"] == CHANNEL_LABEL[ch] and start <= r["created_at"].astimezone(IST).date() < end
            )
        trend.append(point)
    return {**per_channel, "summary": _summary(rows), "by_channel": by_channel, "weekly_trend": trend, "campaigns": rows[:50]}


@comm_router.post("/campaigns", status_code=status.HTTP_201_CREATED, summary="Create a campaign from the dashboard")
async def quick_campaign(payload: QuickCampaign, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    c = await create_campaign(
        db, channel=payload.channel, name=payload.name, message=payload.message, created_by=current_user.id,
        group_ids=payload.groupIds, declared_total=payload.recipients,
    )
    await log_activity(db, actor_id=current_user.id, action_type="campaign_added", module="Communication",
                       reference_id=c.id, description=f"Created {payload.channel} campaign {c.name}")
    await db.commit()
    return (await _rows(db, [c]))[0]


@comm_router.delete("/campaigns/{campaign_id}", summary="Delete a campaign (cancels unsent messages)")
async def delete_any_campaign(campaign_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    await _delete_campaign(db, await _get_campaign(db, campaign_id), current_user)
    return {"success": True}


@comm_router.get("/groups", summary="Recipient groups")
async def comm_groups(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    return await list_groups(db)


@comm_router.post("/recipients", summary="People in the selected groups (preview)")
async def comm_recipients(payload: RecipientsRequest, db: DbSession, current_user: CanView,
                          limit: int = Query(500, ge=1, le=5000)) -> dict[str, Any]:
    everyone = await resolve_recipients(db, payload.groupIds)
    return {"total": len(everyone), "recipients": everyone[:limit]}


# --- campaign analytics ----------------------------------------------------------------


async def _analytics_rows(db, from_date: date | None, to_date: date | None, channel: str | None) -> list[dict[str, Any]]:
    since = datetime.combine(from_date, time.min, IST) if from_date else None
    until = datetime.combine(to_date + timedelta(days=1), time.min, IST) if to_date else None
    ch = None
    if channel and channel.lower() not in ("all", "all channels"):
        ch = normalize_channel(channel)
    return await _rows(db, await _campaigns(db, ch, since=since, until=until))


@analytics_router.get("", summary="Campaign analytics")
async def campaign_analytics(
    db: DbSession,
    current_user: CanView,
    from_date: date | None = Query(None, alias="fromDate"),
    to_date: date | None = Query(None, alias="toDate"),
    channel: str | None = Query(None, alias="channelFilter"),
) -> dict[str, Any]:
    rows = await _analytics_rows(db, from_date, to_date, channel)
    days: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = r["created_at"].astimezone(IST).date().isoformat()
        point = days.setdefault(d, {"date": d, "whatsapp": 0, "sms": 0, "email": 0, "voice": 0, "push": 0})
        key = r["channel"].lower()
        point[key] = point.get(key, 0) + r["total"]
    return {
        "summary": _summary(rows),
        "by_channel": {ch: sum(r["total"] for r in rows if r["channel"] == CHANNEL_LABEL[ch]) for ch in MESSAGE_CHANNELS},
        "daily_trend": sorted(days.values(), key=lambda p: p["date"]),
        "campaigns": rows,
    }


@analytics_router.get("/export", summary="Campaign analytics as CSV", response_class=Response,
                      responses={200: {"content": {"text/csv": {}}}})
async def export_analytics(
    db: DbSession,
    current_user: CanDownload,
    from_date: date | None = Query(None, alias="fromDate"),
    to_date: date | None = Query(None, alias="toDate"),
    channel: str | None = Query(None, alias="channelFilter"),
) -> Response:
    rows = await _analytics_rows(db, from_date, to_date, channel)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Campaign", "Channel", "Date & Time", "Total", "Delivered", "Read", "Failed", "Status"])
    for r in rows:
        w.writerow([r["name"], r["channel"], r["date_time"], r["total"], r["delivered"], r["read"], r["failed"], r["status"]])
    return Response(
        content=("﻿" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="campaign_analytics.csv"'},
    )


# --- WhatsApp -----------------------------------------------------------------------------


class SendCampaign(BaseModel):
    """WhatsApp / SMS / AI-call campaign form. Accepts the field names each page uses."""

    model_config = ConfigDict(extra="ignore")

    campaignName: str = Field(default="Untitled Campaign", max_length=200, validation_alias=AliasChoices("campaignName", "name"))
    groupIds: list[str] = Field(default_factory=list, validation_alias=AliasChoices("groupIds", "selectedGroupIds", "group_ids"))
    extraNumbers: list[str] = Field(default_factory=list, validation_alias=AliasChoices("extraNumbers", "numbers", "recipients"))
    message: str | None = Field(default=None, validation_alias=AliasChoices("message", "messageText", "script", "text"))
    messageType: str | None = None
    mediaUrl: str | None = None
    sendSchedule: str = "now"
    scheduleDate: str | None = None
    scheduleTime: str | None = None
    smsType: str | None = None
    dltTemplateId: str | None = None
    totalRecipients: int | None = None
    language: str | None = None


class TestMessage(BaseModel):
    number: str = Field(min_length=10, max_length=15)
    message: str | None = None


@whatsapp_router.get("/groups", summary="WhatsApp recipient groups")
async def whatsapp_groups(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    return await list_groups(db)


@whatsapp_router.post("/recipients", summary="getSelectedRecipients(groupIds)")
async def whatsapp_recipients(payload: RecipientsRequest, db: DbSession, current_user: CanView,
                              limit: int = Query(500, ge=1, le=5000)) -> list[dict[str, Any]]:
    return (await resolve_recipients(db, payload.groupIds))[:limit]


@whatsapp_router.post("/test", summary="sendTestMessage(number)")
async def whatsapp_test(payload: TestMessage, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    queue_message(db, channel="whatsapp", recipient=payload.number, body=payload.message or "Test message from MLA office",
                  source="test")
    await db.commit()
    return {"success": True, "message": f"Test WhatsApp message queued for {payload.number}"}


async def _send(db, channel: str, payload: SendCampaign, user, **extra) -> CommCampaign:
    if not payload.groupIds and not payload.extraNumbers:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one recipient group or number")
    if not (payload.message or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message is required")
    c = await create_campaign(
        db, channel=channel, name=payload.campaignName, message=payload.message, created_by=user.id,
        group_ids=payload.groupIds, extra_recipients=payload.extraNumbers,
        scheduled_for=parse_schedule(payload.sendSchedule, payload.scheduleDate, payload.scheduleTime),
        declared_total=payload.totalRecipients, **extra,
    )
    await log_activity(db, actor_id=user.id, action_type="campaign_added", module="Communication", reference_id=c.id,
                       description=f"{CHANNEL_LABEL[c.channel]} campaign {c.name} to {c.total_recipients} people")
    await db.commit()
    return c


@whatsapp_router.get("/campaigns", summary="WhatsApp campaigns")
async def whatsapp_campaigns(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    return await _rows(db, await _campaigns(db, "whatsapp"))


@whatsapp_router.post("/campaigns", status_code=status.HTTP_201_CREATED, summary="submitCampaign(payload)")
async def whatsapp_send(payload: SendCampaign, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    c = await _send(db, "whatsapp", payload, current_user, message_type=payload.messageType, media_url=payload.mediaUrl)
    return {"success": True, **(await _rows(db, [c]))[0]}


# --- message templates (WhatsApp / Email / SMS) --------------------------------------------


class TemplateForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    channel: str = "WhatsApp"
    subject: str | None = None
    message: str = Field(min_length=1, validation_alias=AliasChoices("message", "text", "body"))
    dlt_id: str | None = None


TEMPLATE_PREFIX = {"WhatsApp": "TPL", "Email": "ET", "SMS": "DLT"}


def _channel_label(value: str) -> str:
    v = (value or "WhatsApp").strip().lower()
    return {"whatsapp": "WhatsApp", "email": "Email", "sms": "SMS"}.get(v, "WhatsApp")


def template_row(t: MessageTemplate) -> dict[str, Any]:
    return {
        "id": format_id(TEMPLATE_PREFIX.get(t.channel, "TPL"), t.id),
        "name": t.name,
        "channel": t.channel,
        "subject": t.subject,
        "message": t.message,
        "text": t.message,
        "dlt_id": t.dlt_id,
        "updated_at": (t.updated_at or t.created_at).astimezone(IST).strftime("%d %b %Y"),
    }


@templates_router.get("", summary="getTemplates(channel)")
async def get_templates(db: DbSession, current_user: CanView, channel: str = Query("WhatsApp")) -> list[dict[str, Any]]:
    stmt = select(MessageTemplate).where(MessageTemplate.channel == _channel_label(channel)).order_by(MessageTemplate.id.desc())
    return [template_row(t) for t in (await db.execute(stmt)).scalars().all()]


@templates_router.post("", status_code=status.HTTP_201_CREATED, summary="createTemplate(data)")
async def create_template(payload: TemplateForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    t = MessageTemplate(channel=_channel_label(payload.channel), name=payload.name, subject=payload.subject,
                        message=payload.message, dlt_id=payload.dlt_id, created_by=current_user.id)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return template_row(t)


@templates_router.put("/{template_id}", summary="Edit a template")
async def update_template(template_id: str, payload: TemplateForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    t = await db.get(MessageTemplate, parse_id(template_id, label="Template"))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    t.name, t.subject, t.message, t.dlt_id = payload.name, payload.subject, payload.message, payload.dlt_id
    await db.commit()
    await db.refresh(t)
    return template_row(t)


@templates_router.delete("/{template_id}", summary="deleteTemplate(id)")
async def delete_template(template_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    t = await db.get(MessageTemplate, parse_id(template_id, label="Template"))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    await db.delete(t)
    await db.commit()
    return {"success": True}


# --- Email ---------------------------------------------------------------------------------


class EmailCampaignForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recipients: list[str] = Field(min_length=1)
    campaignName: str = Field(default="Untitled Email Campaign", max_length=200)
    subject: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    sendSchedule: str = "now"
    scheduleDate: str | None = None
    scheduleTime: str | None = None


def email_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"].replace("CMP-", "EC-"),
        "name": r["name"],
        "subject": r["subject"],
        "recipients_count": r["total"],
        "sent_at": r["date_time"],
        "status": r["status"],
        "delivered": r["delivered"],
        "failed": r["failed"],
    }


@email_router.get("/campaigns", summary="getRecentCampaigns()")
async def email_campaigns(db: DbSession, current_user: CanView, limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    return [email_row(r) for r in await _rows(db, await _campaigns(db, "email", limit=limit))]


@email_router.post("/campaigns", status_code=status.HTTP_201_CREATED, summary="sendEmailCampaign(payload)")
async def send_email_campaign(payload: EmailCampaignForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    bad = [r for r in payload.recipients if "@" not in r or "." not in r.split("@")[-1]]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid email address(es): {', '.join(bad[:5])}")
    c = await create_campaign(
        db, channel="email", name=payload.campaignName, message=payload.message, created_by=current_user.id,
        recipients=[{"name": None, "mobile": r.strip(), "village": None} for r in payload.recipients],
        scheduled_for=parse_schedule(payload.sendSchedule, payload.scheduleDate, payload.scheduleTime),
        subject=payload.subject,
    )
    await log_activity(db, actor_id=current_user.id, action_type="campaign_added", module="Communication", reference_id=c.id,
                       description=f"Email campaign {c.name} to {c.total_recipients} recipients")
    await db.commit()
    return email_row((await _rows(db, [c]))[0])


# --- SMS -------------------------------------------------------------------------------------


@sms_router.get("/groups", summary="SMS recipient groups")
async def sms_groups(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    return await list_groups(db)


@sms_router.get("/dlt-templates", summary="getDltTemplates()")
async def dlt_templates(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    stmt = select(MessageTemplate).where(MessageTemplate.channel == "SMS").order_by(MessageTemplate.id)
    return [template_row(t) for t in (await db.execute(stmt)).scalars().all()]


@sms_router.post("/dlt-templates", status_code=status.HTTP_201_CREATED, summary="Register a DLT-approved SMS template")
async def add_dlt_template(payload: TemplateForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    if not payload.dlt_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "dlt_id is required for SMS templates")
    t = MessageTemplate(channel="SMS", name=payload.name, message=payload.message, dlt_id=payload.dlt_id,
                        created_by=current_user.id)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return template_row(t)


@sms_router.delete("/dlt-templates/{template_id}", summary="Remove a DLT template")
async def delete_dlt_template(template_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    return await delete_template(template_id, db, current_user)


def sms_row(r: dict[str, Any], c: CommCampaign) -> dict[str, Any]:
    return {
        "id": r["id"].replace("CMP-", "SMS-"),
        "name": r["name"],
        "sms_type": c.sms_type,
        "recipients_count": r["total"],
        "date_time": r["date_time"],
        "status": r["status"],
    }


@sms_router.get("/campaigns", summary="getEarlierCampaigns()")
async def sms_campaigns(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    campaigns = await _campaigns(db, "sms")
    rows = await _rows(db, campaigns)
    return [sms_row(r, c) for r, c in zip(rows, campaigns)]


@sms_router.post("/campaigns", status_code=status.HTTP_201_CREATED, summary="sendSmsCampaign(payload)")
async def send_sms_campaign(payload: SendCampaign, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    message = payload.message
    if not message and payload.dltTemplateId:
        t = await db.get(MessageTemplate, parse_id(payload.dltTemplateId, label="Template"))
        message = t.message if t else None
        payload = payload.model_copy(update={"message": message})
    c = await _send(db, "sms", payload, current_user, sms_type=payload.smsType, dlt_template_id=payload.dltTemplateId)
    return sms_row((await _rows(db, [c]))[0], c)


# --- push notifications ------------------------------------------------------------------------


class PushForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    targetPage: str | None = None


@push_router.get("", summary="getSentNotifications()")
async def sent_notifications(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    rows = []
    for c in await _campaigns(db, "push"):
        rows.append({
            "id": format_id("NOTIF", c.id), "title": c.subject, "message": c.message, "target_page": c.target_page,
            "sent_at": fmt_dt(c.created_at), "status": c.status,
        })
    return rows


@push_router.post("", status_code=status.HTTP_201_CREATED, summary="sendNotification(payload)")
async def send_notification(payload: PushForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    c = CommCampaign(name=payload.title, channel="push", subject=payload.title, message=payload.message,
                     target_page=payload.targetPage, status="Queued", created_by=current_user.id)
    db.add(c)
    await db.flush()
    queue_message(db, channel="push", recipient="all-app-users", subject=payload.title, body=payload.message,
                  source="campaign", source_id=c.id)
    await log_activity(db, actor_id=current_user.id, action_type="push_sent", module="Communication", reference_id=c.id,
                       description=f"Push notification: {payload.title}")
    await db.commit()
    return {"id": format_id("NOTIF", c.id), "title": c.subject, "message": c.message, "target_page": c.target_page,
            "sent_at": fmt_dt(c.created_at or datetime.now(timezone.utc)), "status": c.status}


# --- AI calling agent ---------------------------------------------------------------------------


def ai_row(r: dict[str, Any], c: CommCampaign) -> dict[str, Any]:
    return {
        "id": r["id"].replace("CMP-", "CALL-"),
        "name": r["name"],
        "groups_count": len(c.group_ids or []),
        "recipients_count": r["total"],
        "script": c.message,
        "language": c.language,
        "scheduled_for": "Immediate" if not c.scheduled_for else fmt_dt(c.scheduled_for),
        "status": r["status"],
    }


@ai_router.get("/groups", summary="AI calling recipient groups")
async def ai_groups(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    return await list_groups(db)


@ai_router.get("/campaigns", summary="getCampaigns()")
async def ai_campaigns(db: DbSession, current_user: CanView) -> list[dict[str, Any]]:
    campaigns = await _campaigns(db, "voice")
    rows = await _rows(db, campaigns)
    return [ai_row(r, c) for r, c in zip(rows, campaigns)]


@ai_router.post("/campaigns", status_code=status.HTTP_201_CREATED, summary="queueCampaign(payload)")
async def queue_ai_campaign(payload: SendCampaign, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    c = await _send(db, "voice", payload, current_user, language=payload.language)
    return ai_row((await _rows(db, [c]))[0], c)


@ai_router.delete("/campaigns/{campaign_id}", summary="Delete an AI calling campaign")
async def delete_ai_campaign(campaign_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    await _delete_campaign(db, await _get_campaign(db, campaign_id, "voice"), current_user)
    return {"success": True}


ROUTERS = [comm_router, analytics_router, whatsapp_router, templates_router, email_router, sms_router, push_router, ai_router]

