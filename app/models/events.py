from datetime import date, time

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("status IN ('upcoming','completed','cancelled')", name="ck_events_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(100))
    venue: Mapped[str | None] = mapped_column(String(200))
    chief_guest: Mapped[str | None] = mapped_column(String(150))
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time | None] = mapped_column(Time)
    expected_attendance: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="upcoming", server_default="upcoming")
    photo_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id"))
