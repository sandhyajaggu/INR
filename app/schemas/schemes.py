from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SchemeBase(BaseModel):
    scheme_code: str
    scheme_name: str
    short_description: str | None = None
    detailed_description: str | None = None
    badge_text: str | None = None
    service_provider: str | None = None
    category: str | None = None
    launch_date: date | None = None
    status: str = Field(default="active", pattern="^(active|inactive)$")


class SchemeCreate(SchemeBase):
    pass


class SchemeUpdate(SchemeBase):
    pass


class SchemeOut(SchemeBase, ORMModel):
    id: int
    created_at: datetime
