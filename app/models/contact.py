from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContactMessage(Base):
    __tablename__ = "contact_messages"
    __table_args__ = (
        CheckConstraint("status IN ('new','read','responded')", name="ck_contact_messages_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id"))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(150))
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", server_default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
