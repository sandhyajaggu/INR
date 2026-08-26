from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class MandalOut(ORMModel):
    id: int
    name: str
    created_at: datetime


class VillageOut(ORMModel):
    id: int
    mandal_id: int
    name: str
    created_at: datetime


class BoothCreate(BaseModel):
    booth_number: str
    booth_name: str | None = None
    village_name: str
    mandal_name: str
    location_address: str | None = None
    total_voters: int | None = 0
    booth_officer_name: str | None = None
    booth_officer_mobile: str | None = None


class BoothUpdate(BoothCreate):
    pass


class BoothOut(ORMModel):
    id: int
    booth_number: str
    booth_name: str | None
    village_id: int
    mandal_id: int
    location_address: str | None
    total_voters: int | None
    booth_officer_name: str | None
    booth_officer_mobile: str | None
    created_at: datetime
