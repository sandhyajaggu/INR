from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Family(Base):
    """Families page: a household headed by one voter.

    head_name / mobile / mandal / village / booth_no / members_count /
    schemes_availed are editable on the Edit Family form, so they are stored
    rather than derived. members_count is also kept in step automatically
    when members are added.
    """

    __tablename__ = "families"
    __table_args__ = (UniqueConstraint("head_voter_id", name="uq_families_head_voter_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    head_voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id", ondelete="CASCADE"), nullable=False)
    head_name: Mapped[str] = mapped_column(String(150), nullable=False)
    mobile: Mapped[str | None] = mapped_column(String(15))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    booth_no: Mapped[str | None] = mapped_column(String(20))
    members_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    schemes_availed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    children_under_18: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="family", cascade="all, delete-orphan", order_by="FamilyMember.id"
    )


class FamilyMember(Base):
    __tablename__ = "family_members"
    __table_args__ = (
        UniqueConstraint("voter_id", name="uq_family_members_voter_id"),
        Index("idx_family_members_family_id", "family_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), nullable=False)
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id", ondelete="CASCADE"), nullable=False)
    relation: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped[Family] = relationship(back_populates="members")
