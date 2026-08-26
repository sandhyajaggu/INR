from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DevelopmentWork(Base):
    __tablename__ = "development_works"
    __table_args__ = (
        CheckConstraint("status IN ('pending','in_progress','completed')", name="ck_devworks_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), nullable=False)
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    work_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", onupdate=func.now())
