from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Scheme(Base):
    __tablename__ = "schemes"
    __table_args__ = (CheckConstraint("status IN ('active','inactive')", name="ck_schemes_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    scheme_name: Mapped[str] = mapped_column(String(150), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text)
    detailed_description: Mapped[str | None] = mapped_column(Text)
    badge_text: Mapped[str | None] = mapped_column(String(100))
    service_provider: Mapped[str | None] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(100))
    launch_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','disbursed')", name="ck_beneficiaries_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("schemes.id"), nullable=False)
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id"))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    beneficiary_name: Mapped[str] = mapped_column(String(150), nullable=False)
    relation_name: Mapped[str | None] = mapped_column(String(150))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(10))
    aadhaar_number: Mapped[str | None] = mapped_column(String(255))  # encrypted at rest
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    bank_account_number: Mapped[str | None] = mapped_column(String(30))
    ifsc_code: Mapped[str | None] = mapped_column(String(15))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"), nullable=False)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), nullable=False)
    application_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    photo_url: Mapped[str | None] = mapped_column(Text)
    document_url: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    scheme_details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", onupdate=func.now())
