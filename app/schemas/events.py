from datetime import date, time

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class EventCreate(BaseModel):
    event_title: str
    event_type: str | None = None
    venue: str | None = None
    chief_guest: str | None = None
    village_name: str | None = None
    mandal_name: str | None = None
    event_date: date
    event_time: time | None = None
    expected_attendance: int | None = None
    status: str = Field(default="upcoming", pattern="^(upcoming|completed|cancelled)$")
    description: str | None = None
    photo_url: str | None = None


class EventUpdate(EventCreate):
    pass


class EventOut(ORMModel):
    id: int
    event_title: str
    event_type: str | None
    venue: str | None
    chief_guest: str | None
    village_id: int | None
    mandal_id: int | None
    event_date: date
    event_time: time | None
    expected_attendance: int | None
    status: str
    description: str | None
    photo_url: str | None
    created_by: int | None
