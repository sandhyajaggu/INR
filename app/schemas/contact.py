from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, validate_epic_no


class ContactMessageCreate(BaseModel):
    epic_no: str | None = None
    name: str | None = None
    mobile_number: str | None = None
    village_name: str | None = None
    mandal_name: str | None = None
    message: str

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: str | None) -> str | None:
        return validate_epic_no(v)


class ContactMessageOut(ORMModel):
    id: int
    voter_id: int | None
    epic_no: str | None
    name: str | None
    mobile_number: str | None
    village_id: int | None
    village_name: str | None = None
    mandal_id: int | None
    mandal_name: str | None = None
    message: str
    status: str
    created_at: datetime


class ContactMessageStatusUpdate(BaseModel):
    status: str = Field(pattern="^(new|read|responded)$")


class PublicVoterLookupOut(ORMModel):
    name: str
    mobile: str | None
    village_id: int
    village_name: str
    mandal_id: int
    mandal_name: str
