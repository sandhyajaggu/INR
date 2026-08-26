from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LocalLeader(Base):
    __tablename__ = "local_leaders"

    id: Mapped[int] = mapped_column(primary_key=True)
    leader_name: Mapped[str] = mapped_column(String(150), nullable=False)
    alias_name: Mapped[str | None] = mapped_column(String(150))
    position: Mapped[str | None] = mapped_column(String(100))
    party: Mapped[str | None] = mapped_column(String(100))
    voter_id: Mapped[int | None] = mapped_column(ForeignKey("voters.id"))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    aadhaar_number: Mapped[str | None] = mapped_column(String(255))  # encrypted at rest
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"), nullable=False)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), nullable=False)
    date_joined: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    photo_url: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
