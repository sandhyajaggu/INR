from pydantic import BaseModel

from app.schemas.common import ORMModel


class AppSettingsUpdate(BaseModel):
    constituency_name: str | None = None
    constituency_no: str | None = None
    state: str | None = None
    district: str | None = None
    lok_sabha_constituency: str | None = None
    current_mla: str | None = None
    year_established: int | None = None
    total_mandals: int | None = None
    total_villages: int | None = None
    total_population: int | None = None
    office_address: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class AppSettingsOut(AppSettingsUpdate, ORMModel):
    id: int
