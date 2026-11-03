from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

CMRF_STATUSES = ("Pending", "Under Review", "Approved", "Rejected")


class CmrfApplication(Base):
    """CMRF Applications page (frontend: CMRF.jsx / CMRFFormModal / CMRFDrawer).

    `documents` is a list of {"type", "name", "url"} attached from the drawer.
    """

    __tablename__ = "cmrf_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Pending','Under Review','Approved','Rejected')", name="ck_cmrf_applications_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_name: Mapped[str] = mapped_column(String(150), nullable=False)
    mobile: Mapped[str] = mapped_column(String(15), nullable=False)
    caste: Mapped[str | None] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    hospital: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), nullable=False)
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"), nullable=False)
    epic_no: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending", server_default="Pending")
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    remarks: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
