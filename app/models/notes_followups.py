from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NoteFollowup(Base):
    __tablename__ = "notes_followups"
    __table_args__ = (
        CheckConstraint("priority IN ('low','medium','high')", name="ck_notes_priority"),
        CheckConstraint("status IN ('open','in_progress','closed')", name="ck_notes_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str | None] = mapped_column(String(200))
    related_person: Mapped[str | None] = mapped_column(String(150))
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id"))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    category: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[str | None] = mapped_column(String(10))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    notes_description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
