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
