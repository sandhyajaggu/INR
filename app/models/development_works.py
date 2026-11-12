from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DevelopmentWork(Base):
    __tablename__ = "development_works"
    __table_args__ = (
        CheckConstraint("status IN ('Not Started','In Progress','Completed')", name="ck_devworks_status"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_devworks_progress"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    te: Mapped[dict | None] = mapped_column(JSONB)  # Telugu text per field, see app/core/telugu.py
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), nullable=False)
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Not Started", server_default="Not Started"
    )
    work_date: Mapped[date | None] = mapped_column(Date)
    # Development Works page fields
    fund_source: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    completion_date: Mapped[date | None] = mapped_column(Date)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    contractor: Mapped[str | None] = mapped_column(String(200))
    contractor_te: Mapped[str | None] = mapped_column(String(200))
    photo_url: Mapped[str | None] = mapped_column(Text)
    completed_photo_url: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
