from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DevelopmentWorkCreate(BaseModel):
    title: str
    category: str | None = None
    mandal_name: str
    village_name: str | None = None
    estimated_cost: Decimal | None = None
    description: str | None = None
    status: str = Field(default="pending", pattern="^(pending|in_progress|completed)$")
    work_date: date | None = None


class DevelopmentWorkUpdate(DevelopmentWorkCreate):
    pass


class DevelopmentWorkOut(ORMModel):
    id: int
    title: str
    category: str | None
    mandal_id: int
    village_id: int | None
    estimated_cost: Decimal | None
    description: str | None
    status: str
    work_date: date | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class DevelopmentStatusSummary(BaseModel):
    status: str
    total: int
