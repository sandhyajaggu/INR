from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    constituency_name: Mapped[str | None] = mapped_column(String(150))
    constituency_no: Mapped[str | None] = mapped_column(String(20))
    state: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    lok_sabha_constituency: Mapped[str | None] = mapped_column(String(150))
    current_mla: Mapped[str | None] = mapped_column(String(150))
    year_established: Mapped[int | None] = mapped_column(Integer)
    total_mandals: Mapped[int | None] = mapped_column(Integer)
    total_villages: Mapped[int | None] = mapped_column(Integer)
    total_population: Mapped[int | None] = mapped_column(BigInteger)
    office_address: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(150))
    contact_phone: Mapped[str | None] = mapped_column(String(15))
