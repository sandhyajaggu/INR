"""Models for Public Enquiries, the message outbox, birthdays, voter surveys and media albums."""

from datetime import date, datetime

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MediaAlbum(Base):
    """Media & Gallery page: a photo album (cover + list of photo URLs)."""

    __tablename__ = "media_albums"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    album_date: Mapped[date | None] = mapped_column(Date)
    cover_url: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PublicEnquiry(Base):
    """Contact page submission (Public Enquiry Requests page).

    `feedback` holds the optional 9-question voter feedback used by the
    Election Pulse (satisfiedWithMLA, easeOfMeeting, villageDeveloped,
    schemesReaching, voteToday, expectToWin, whatMattersMost, likelyToVote,
    suggestion).
    """

    __tablename__ = "public_enquiries"
    __table_args__ = (
        CheckConstraint("status IN ('New','In Progress','Resolved')", name="ck_public_enquiries_status"),
        Index("idx_public_enquiries_mobile", "mobile"),
        Index("idx_public_enquiries_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    citizen_name: Mapped[str] = mapped_column(String(150), nullable=False)
    epic_no: Mapped[str | None] = mapped_column(String(20))
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id", ondelete="SET NULL"))
    constituency: Mapped[str | None] = mapped_column(String(100))
    enquiry_type: Mapped[str] = mapped_column(String(100), nullable=False)
    mandal: Mapped[str | None] = mapped_column(String(100))
    village: Mapped[str | None] = mapped_column(String(150))
    mobile: Mapped[str] = mapped_column(String(15), nullable=False)
    email: Mapped[str | None] = mapped_column(String(150))
    message: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    voice_url: Mapped[str | None] = mapped_column(Text)
    voice_duration: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="New", server_default="New")
    feedback: Mapped[dict | None] = mapped_column(JSONB)
    matched_in_voter_list: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OutboxMessage(Base):
    """Every outgoing message (WhatsApp, SMS, email, voice call, push).

    Messages are queued here with status Queued / Scheduled. A provider
    integration (not connected yet) picks them up and moves them to
    Sent / Delivered / Read / Failed; the analytics pages read these rows.
    """

    __tablename__ = "message_outbox"
    __table_args__ = (
        CheckConstraint("channel IN ('whatsapp','sms','email','voice','push')", name="ck_outbox_channel"),
        CheckConstraint(
            "status IN ('Queued','Scheduled','Sent','Delivered','Read','Failed','Cancelled')", name="ck_outbox_status"
        ),
        Index("idx_outbox_source", "source", "source_id"),
        Index("idx_outbox_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(String(150))
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Queued", server_default="Queued")
    error: Mapped[str | None] = mapped_column(Text)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BirthdayWish(Base):
    __tablename__ = "birthday_wishes"
    __table_args__ = (UniqueConstraint("voter_id", "wish_date", name="uq_birthday_wishes_voter_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id", ondelete="CASCADE"), nullable=False)
    wish_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Scheduled", server_default="Scheduled")
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("message_outbox.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MobileOtp(Base):
    __tablename__ = "mobile_otps"

    id: Mapped[int] = mapped_column(primary_key=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id", ondelete="CASCADE"), nullable=False)
    mobile: Mapped[str] = mapped_column(String(15), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SurveyCampaign(Base):
    """Surveys page "Campaigns by channel" (and NewSurvey publish)."""

    __tablename__ = "survey_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    feedback_filter: Mapped[str | None] = mapped_column(String(50))
    target: Mapped[int] = mapped_column(Integer, nullable=False, default=1000, server_default=text("1000"))
    responses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    positive: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    negative: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Running", server_default="Running")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    post_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VoterSurvey(Base):
    """One door-to-door survey of a voter (VoterSurveyModal)."""

    __tablename__ = "voter_surveys"
    __table_args__ = (Index("idx_voter_surveys_voter_id", "voter_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id", ondelete="CASCADE"), nullable=False)
    survey_type: Mapped[str] = mapped_column(String(100), nullable=False)
    part_a: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    answers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    added_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    party_support: Mapped[str | None] = mapped_column(String(30))
    party_member: Mapped[str | None] = mapped_column(String(10))
    member_party: Mapped[str | None] = mapped_column(String(30))
    membership_id: Mapped[str | None] = mapped_column(String(50))
    household_status: Mapped[str | None] = mapped_column(String(50))
    escalation: Mapped[str | None] = mapped_column(String(50))
    field_notes: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(String(20))
    surveyed_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    surveyed_by_name: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WarRoomAlert(Base):
    """Raised when a survey records an escalation (VIP alert / Grievance fix)."""

    __tablename__ = "war_room_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id", ondelete="CASCADE"), nullable=False)
    survey_id: Mapped[int | None] = mapped_column(ForeignKey("voter_surveys.id", ondelete="SET NULL"))
    escalation: Mapped[str] = mapped_column(String(50), nullable=False)
    household: Mapped[str | None] = mapped_column(String(50))
    field_notes: Mapped[str | None] = mapped_column(Text)
    booth_agent: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Pending Action", server_default="Pending Action")
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
