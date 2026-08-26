from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (
        CheckConstraint("satisfaction_rating BETWEEN 1 AND 5", name="ck_surveys_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    respondent_name: Mapped[str | None] = mapped_column(String(150))
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id"))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(50))
    feedback_type: Mapped[str | None] = mapped_column(String(50))
    satisfaction_rating: Mapped[int | None] = mapped_column(SmallInteger)
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    survey_date: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    photo_url: Mapped[str | None] = mapped_column(Text)
    feedback_details: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id"))
