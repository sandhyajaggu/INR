from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Mandal(Base):
    __tablename__ = "mandals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    villages: Mapped[list["Village"]] = relationship(back_populates="mandal")


class Village(Base):
    __tablename__ = "villages"
    __table_args__ = (UniqueConstraint("mandal_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    mandal: Mapped["Mandal"] = relationship(back_populates="villages")


class VillageAlias(Base):
    """An alternate spelling of a village name accepted on bulk-import lookups.

    Real electoral-roll sheets carry inconsistent, non-canonical spellings
    of village names (ALL CAPS, missing spaces, transliteration variants).
    Rather than renaming every uploaded sheet to match the canonical
    villages.name, known variants are registered here so bulk-import
    resolves either spelling to the same village_id — voters aren't split
    across duplicate village records depending on which spelling their
    sheet happened to use.
    """

    __tablename__ = "village_aliases"
    __table_args__ = (UniqueConstraint("mandal_id", "alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id", ondelete="CASCADE"), nullable=False)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    village: Mapped["Village"] = relationship()


class Booth(Base):
    __tablename__ = "booths"
    __table_args__ = (UniqueConstraint("mandal_id", "booth_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booth_number: Mapped[str] = mapped_column(String(20), nullable=False)
    booth_name: Mapped[str | None] = mapped_column(String(150))
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"), nullable=False)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id", ondelete="RESTRICT"), nullable=False)
    location_address: Mapped[str | None] = mapped_column(Text)
    total_voters: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    booth_officer_name: Mapped[str | None] = mapped_column(String(150))
    booth_officer_mobile: Mapped[str | None] = mapped_column(String(15))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
