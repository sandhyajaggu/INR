from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Voter(Base):
    __tablename__ = "voters"
    __table_args__ = (
        CheckConstraint("gender IN ('Male','Female','Other')", name="ck_voters_gender"),
        # Backs pg_trgm fuzzy name search (see voter_service.search_voters).
        # Requires `CREATE EXTENSION IF NOT EXISTS pg_trgm` — added by hand to
        # the first Alembic migration since autogenerate won't create extensions.
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", onupdate=func.now())
