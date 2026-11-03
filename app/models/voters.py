from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Voter(Base):
    __tablename__ = "voters"
    __table_args__ = (
        CheckConstraint("gender IN ('Male','Female','Other')", name="ck_voters_gender"),
        CheckConstraint("status IN ('Verified','Pending')", name="ck_voters_status"),
        CheckConstraint("polling_status IN ('voted','not_voted')", name="ck_voters_polling_status"),
        # Backs pg_trgm fuzzy name search (see voter_service.search_voters).
        # Requires `CREATE EXTENSION IF NOT EXISTS pg_trgm` — added by hand to
        # the first Alembic migration since autogenerate won't create extensions.
        Index("idx_voters_removed_at", "removed_at"),
        Index("idx_voters_booth_id", "booth_id"),
        Index("idx_voters_mandal_id", "mandal_id"),
        Index("idx_voters_dob", "dob"),
        Index("idx_voters_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    epic_no: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    relation_name: Mapped[str | None] = mapped_column(String(150))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(10))
    mobile: Mapped[str | None] = mapped_column(String(15))
    aadhaar_number: Mapped[str | None] = mapped_column(String(255))  # encrypted at rest
    house_no: Mapped[str | None] = mapped_column(String(50))
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"), nullable=False)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), nullable=False)
    booth_id: Mapped[int | None] = mapped_column(ForeignKey("booths.id"))
    voted_last_election: Mapped[bool | None] = mapped_column(Boolean)
    is_new_voter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    photo_url: Mapped[str | None] = mapped_column(Text)
    # Voters page fields
    relation_type: Mapped[str | None] = mapped_column(String(10))  # S/o, W/o, D/o, H/o
    religion: Mapped[str | None] = mapped_column(String(30))
    caste_category: Mapped[str | None] = mapped_column(String(20))
    alt_mobile: Mapped[str | None] = mapped_column(String(15))
    dob: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending", server_default="Pending")
    mobile_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Removed voters (soft removal; restore clears these)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removal_reason: Mapped[str | None] = mapped_column(String(50))
    removal_details: Mapped[str | None] = mapped_column(Text)
    removed_by: Mapped[str | None] = mapped_column(String(150))
    # Polling Day marking
    polling_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_voted", server_default="not_voted"
    )
    voted_party: Mapped[str | None] = mapped_column(String(30))
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    marked_by: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
