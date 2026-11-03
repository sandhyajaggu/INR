"""Recipient groups, campaign creation and delivery stats for the communication pages.

Recipient groups (WhatsApp / SMS / AI calling / broadcast lists):
    all_voters, <mandal>_voters (one per mandal), new_voters, booth_agents,
    scheme_beneficiaries, cmrf_applicants, family_heads, list_<id> (saved broadcast lists)
Counts are of reachable people (with a mobile number), de-duplicated by mobile.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import format_id
from app.models.cmrf import CmrfApplication
from app.models.communication import BroadcastList, CommCampaign
from app.models.engagement import OutboxMessage
from app.models.families import Family
from app.models.geography import Booth, Mandal, Village
from app.models.schemes import Beneficiary, Scheme
from app.models.voters import Voter
from app.services.outbox_service import normalize_channel, personalize

IST = timezone(timedelta(hours=5, minutes=30))
CHANNEL_LABEL = {"whatsapp": "WhatsApp", "sms": "SMS", "email": "Email", "voice": "Voice", "push": "Push"}
DONE_STATUSES = ("Sent", "Delivered", "Read")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


async def _mandals(db: AsyncSession) -> list[tuple[int, str]]:
    return list((await db.execute(select(Mandal.id, Mandal.name).order_by(Mandal.id))).all())


def _voter_query():
    return (
        select(Voter.name, Voter.mobile, Village.name.label("village"))
        .join(Village, Village.id == Voter.village_id)
        .where(Voter.removed_at.is_(None), Voter.mobile.is_not(None), Voter.mobile != "")
    )


async def _group_queries(db: AsyncSession) -> dict[str, tuple[str, str, Any]]:
    """group id -> (label, icon, select(name, mobile, village))."""
    groups: dict[str, tuple[str, str, Any]] = {"all_voters": ("All Voters", "users", _voter_query())}
    for mandal_id, name in await _mandals(db):
        groups[f"{slug(name)}_voters"] = (f"{name} Mandal Voters", "building", _voter_query().where(Voter.mandal_id == mandal_id))
    groups["new_voters"] = ("New Voters", "user-plus", _voter_query().where(Voter.is_new_voter.is_(True)))
    groups["booth_agents"] = (
        "Booth Agents", "id-badge",
        select(Booth.booth_officer_name.label("name"), Booth.booth_officer_mobile.label("mobile"), Village.name.label("village"))
        .join(Village, Village.id == Booth.village_id)
        .where(Booth.booth_officer_mobile.is_not(None)),
    )
    groups["scheme_beneficiaries"] = (
        "Scheme Beneficiaries", "handshake",
        select(Beneficiary.beneficiary_name.label("name"), Beneficiary.mobile_number.label("mobile"), Village.name.label("village"))
        .join(Village, Village.id == Beneficiary.village_id)
        .join(Scheme, Scheme.id == Beneficiary.scheme_id)
        .where(Beneficiary.mobile_number.is_not(None), Scheme.scheme_code != "cmrf"),
    )
    groups["cmrf_applicants"] = (
        "CMRF Applicants", "file-medical",
        select(CmrfApplication.applicant_name.label("name"), CmrfApplication.mobile.label("mobile"), Village.name.label("village"))
        .join(Village, Village.id == CmrfApplication.village_id),
    )
    groups["family_heads"] = (
        "Family Heads", "home",
        select(Family.head_name.label("name"), Family.mobile.label("mobile"), Village.name.label("village"))
        .outerjoin(Village, Village.id == Family.village_id)
        .where(Family.mobile.is_not(None)),
    )
    return groups


async def list_groups(db: AsyncSession, *, include_lists: bool = True) -> list[dict[str, Any]]:
    out = []
    for gid, (label, icon, stmt) in (await _group_queries(db)).items():
        sub = stmt.subquery()
        count = (await db.execute(select(func.count(func.distinct(sub.c.mobile))))).scalar_one()
        out.append({"id": gid, "name": label, "icon": icon, "count": count})
    if include_lists:
        for bl in (await db.execute(select(BroadcastList).order_by(BroadcastList.id.desc()))).scalars().all():
            mobiles = {c.get("mobile") for c in bl.contacts or [] if c.get("mobile")}
            out.append({"id": f"list_{bl.id}", "name": bl.name, "icon": "list", "count": len(mobiles)})
    return out


async def resolve_recipients(
    db: AsyncSession, group_ids: list[str], *, limit: int | None = None
) -> list[dict[str, Any]]:
    """People in the chosen groups, de-duplicated by mobile, each tagged with the group it came from."""
    queries = await _group_queries(db)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for gid in group_ids:
        if gid.startswith("list_") and gid[5:].isdigit():
            bl = await db.get(BroadcastList, int(gid[5:]))
            rows = [(c.get("name"), c.get("mobile"), c.get("village")) for c in (bl.contacts if bl else [])]
            label = bl.name if bl else gid
        elif gid in queries:
            label, _, stmt = queries[gid]
            rows = (await db.execute(stmt)).all()
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown recipient group '{gid}'")
        for name, mobile, village in rows:
            if not mobile or mobile in seen:
                continue
            seen.add(mobile)
            out.append({"id": len(out) + 1, "name": name, "mobile": mobile, "village": village, "from": label})
            if limit and len(out) >= limit:
                return out
    return out


def parse_schedule(send_schedule: str | None, schedule_date: str | None, schedule_time: str | None) -> datetime | None:
    """"now" -> None; "later" + date (YYYY-MM-DD) + time (HH:MM, IST) -> aware datetime."""
    if (send_schedule or "now").lower() == "now" or not schedule_date:
        return None
    try:
        when = datetime.fromisoformat(f"{schedule_date}T{(schedule_time or '09:00')[:5]}").replace(tzinfo=IST)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid schedule date/time") from exc
    if when < datetime.now(timezone.utc) - timedelta(minutes=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Schedule time is in the past")
    return when


async def create_campaign(
    db: AsyncSession,
    *,
    channel: str,
    name: str,
    message: str | None,
    created_by: int | None,
    group_ids: list[str] | None = None,
    extra_recipients: list[str] | None = None,
    recipients: list[dict[str, Any]] | None = None,
    scheduled_for: datetime | None = None,
    declared_total: int | None = None,
    **fields: Any,
) -> CommCampaign:
    """Create a campaign and queue one outbox message per recipient.

    Recipients come from group_ids, extra_recipients (raw mobiles / emails) and/or an explicit
    `recipients` list. When none can be resolved (e.g. a dashboard quick-entry with only a count),
    the campaign is still recorded with declared_total.
    """
    ch = normalize_channel(channel)
    people: list[dict[str, Any]] = list(recipients or [])
    if group_ids:
        people += await resolve_recipients(db, group_ids)
    for raw in extra_recipients or []:
        value = str(raw).strip()
        if value:
            people.append({"name": None, "mobile": value, "village": None})
    seen: set[str] = set()
    unique = []
    for p in people:
        key = (p.get("mobile") or "").strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(p)

    campaign = CommCampaign(
        name=name, channel=ch, message=message, group_ids=group_ids or [], extra_recipients=extra_recipients or [],
        total_recipients=len(unique) if unique else (declared_total or 0), scheduled_for=scheduled_for,
        status="Scheduled" if scheduled_for else "Queued", created_by=created_by, **fields,
    )
    db.add(campaign)
    await db.flush()
    if unique and message is not None:
        today = datetime.now(IST).strftime("%d %b %Y")
        rows = [
            {
                "channel": ch,
                "recipient": p["mobile"],
                "recipient_name": p.get("name"),
                "subject": fields.get("subject"),
                "body": personalize(message, name=p.get("name") or "", village=p.get("village") or "", date=today),
                "source": "campaign",
                "source_id": campaign.id,
                "status": "Scheduled" if scheduled_for else "Queued",
                "scheduled_for": scheduled_for,
            }
            for p in unique
        ]
        for i in range(0, len(rows), 2000):
            await db.execute(insert(OutboxMessage), rows[i : i + 2000])
    return campaign


async def campaign_stats(db: AsyncSession, campaign_ids: list[int]) -> dict[int, dict[str, int]]:
    if not campaign_ids:
        return {}
    stmt = (
        select(OutboxMessage.source_id, OutboxMessage.status, func.count())
        .where(OutboxMessage.source == "campaign", OutboxMessage.source_id.in_(campaign_ids))
        .group_by(OutboxMessage.source_id, OutboxMessage.status)
    )
    out: dict[int, dict[str, int]] = {}
    for cid, st, n in (await db.execute(stmt)).all():
        out.setdefault(cid, {})[st] = n
    return out


def campaign_status(c: CommCampaign, counts: dict[str, int]) -> str:
    if c.status == "Cancelled":
        return "Cancelled"
    if not counts:
        return c.status
    pending = counts.get("Queued", 0) + counts.get("Scheduled", 0)
    if pending:
        return "Scheduled" if counts.get("Scheduled") else "Queued"
    if counts.get("Failed") and not any(counts.get(s) for s in DONE_STATUSES):
        return "Failed"
    return "Sent"


def fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    local = value.astimezone(IST)
    return local.strftime("%d %b %Y, %H:%M")


def campaign_row(c: CommCampaign, counts: dict[str, int] | None) -> dict[str, Any]:
    counts = counts or {}
    delivered = counts.get("Delivered", 0) + counts.get("Read", 0)
    return {
        "id": format_id("CMP", c.id),
        "name": c.name,
        "channel": CHANNEL_LABEL.get(c.channel, c.channel),
        "date_time": fmt_dt(c.scheduled_for or c.created_at),
        "total": c.total_recipients,
        "sent": sum(counts.get(s, 0) for s in DONE_STATUSES),
        "delivered": delivered,
        "read": counts.get("Read", 0),
        "failed": counts.get("Failed", 0),
        "queued": counts.get("Queued", 0) + counts.get("Scheduled", 0),
        "status": campaign_status(c, counts),
        "subject": c.subject,
        "message": c.message,
        "scheduled_for": c.scheduled_for,
        "created_at": c.created_at,
    }
