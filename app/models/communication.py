"""Communication module models (WhatsApp, SMS, email, voice, push, social, calls, meetings)."""

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommCampaign(Base):
    """A send to many people on one channel. Its messages are message_outbox rows
    with source='campaign' and source_id=<this id>."""

    __tablename__ = "comm_campaigns"
    __table_args__ = (Index("idx_comm_campaigns_channel", "channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # whatsapp / sms / email / voice / push
    subject: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    message_type: Mapped[str | None] = mapped_column(String(20))
    media_url: Mapped[str | None] = mapped_column(Text)
    sms_type: Mapped[str | None] = mapped_column(String(20))
    dlt_template_id: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str | None] = mapped_column(String(20))
    target_page: Mapped[str | None] = mapped_column(String(50))
    group_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    extra_recipients: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Queued", server_default="Queued")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # WhatsApp / Email / SMS
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    dlt_id: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BroadcastList(Base):
    __tablename__ = "broadcast_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    made_from: Mapped[str | None] = mapped_column(String(100))
    contacts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    """WhatsApp chat history: one row per message, grouped into chats by mobile."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("direction IN ('in','out')", name="ck_chat_messages_direction"),
        Index("idx_chat_messages_mobile", "mobile", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mobile: Mapped[str] = mapped_column(String(15), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(150))
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SocialPost(Base):
    __tablename__ = "social_posts"
    __table_args__ = (
        CheckConstraint(
            "status_type IN ('scheduled','posted','reminder','failed','cancelled')", name="ck_social_posts_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    post_text: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(Text)
    survey_id: Mapped[str | None] = mapped_column(String(30))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_type: Mapped[str] = mapped_column(String(20), nullable=False, default="reminder", server_default="reminder")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutoReply(Base):
    __tablename__ = "auto_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="WhatsApp", server_default="WhatsApp")
    reply: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VoterCall(Base):
    """Calling to Voters: one logged call."""

    __tablename__ = "voter_calls"
    __table_args__ = (Index("idx_voter_calls_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id", ondelete="SET NULL"))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    person_name: Mapped[str] = mapped_column(String(150), nullable=False)
    mobile: Mapped[str] = mapped_column(String(15), nullable=False)
    village: Mapped[str | None] = mapped_column(String(150))
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    logged_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    logged_by_name: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamMeeting(Base):
    __tablename__ = "team_meetings"
    __table_args__ = (
        CheckConstraint("status IN ('Upcoming','Completed','Cancelled')", name="ck_team_meetings_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    meeting_time: Mapped[time | None] = mapped_column(Time)
    link_or_venue: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Upcoming", server_default="Upcoming")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
