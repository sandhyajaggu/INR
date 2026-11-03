"""Outgoing message queue (WhatsApp / SMS / email / voice call / push).

No messaging provider is connected yet. Everything the dashboard "sends"
(campaigns, birthday wishes, OTPs, test messages, chat replies, push
notifications, AI calls) is written to message_outbox with status Queued
(or Scheduled for a future time). When a provider is wired in, a worker
reads Queued rows due now, sends them and updates status / sent_at /
delivered_at / read_at, and every analytics page picks that up unchanged.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import OutboxMessage

CHANNELS = {"whatsapp", "sms", "email", "voice", "push"}


def normalize_channel(value: str) -> str:
    v = (value or "").strip().lower().replace(" ", "_")
    aliases = {"voice_call": "voice", "call": "voice", "ai_call": "voice", "mail": "email", "notification": "push"}
    v = aliases.get(v, v)
    if v not in CHANNELS:
        raise ValueError(f"Unknown channel '{value}'")
    return v


def queue_message(
    db: AsyncSession,
    *,
    channel: str,
    recipient: str,
    body: str,
    source: str,
    source_id: int | None = None,
    recipient_name: str | None = None,
    subject: str | None = None,
    scheduled_for: datetime | None = None,
) -> OutboxMessage:
    now = datetime.now(timezone.utc)
    msg = OutboxMessage(
        channel=normalize_channel(channel),
        recipient=recipient,
        recipient_name=recipient_name,
        subject=subject,
        body=body,
        source=source,
        source_id=source_id,
        status="Scheduled" if scheduled_for and scheduled_for > now else "Queued",
        scheduled_for=scheduled_for,
    )
    db.add(msg)
    return msg


def personalize(template: str, **values: str | None) -> str:
    """Fills {{name}} / {name} style placeholders; unknown placeholders are left as they are."""
    out = template or ""
    for key, value in values.items():
        if value is None:
            continue
        out = out.replace("{{" + key + "}}", str(value)).replace("{" + key + "}", str(value))
    return out
