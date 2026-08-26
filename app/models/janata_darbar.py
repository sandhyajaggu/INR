from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class JanataDarbarVisit(Base):
    __tablename__ = "janata_darbar_visits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_progress','resolved','referred')", name="ck_janata_darbar_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    visitor_name: Mapped[str] = mapped_column(String(150), nullable=False)
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id"))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(10))
    issue_category: Mapped[str | None] = mapped_column(String(100))
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    visit_date: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    document_url: Mapped[str | None] = mapped_column(Text)
    issue_description: Mapped[str | None] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(Text)
