from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GovernmentOffice(Base):
    """Government Offices page (frontend: GovernmentOffices.jsx / OfficeModals.jsx).

    `category` (revenue_admin / hospitals / schools / police_services) is
    derived from the office type, as the page's summary cards expect.
    """

    __tablename__ = "government_offices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_te: Mapped[str | None] = mapped_column(String(200))
    office_type: Mapped[str] = mapped_column(String(100), nullable=False)
    type_te: Mapped[str | None] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), nullable=False)
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    address_te: Mapped[str | None] = mapped_column(Text)
    contact_number: Mapped[str] = mapped_column(String(30), nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
