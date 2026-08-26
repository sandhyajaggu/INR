from datetime import date

from pydantic import BaseModel, field_validator

from app.schemas.common import ORMModel, validate_epic_no


class LocalLeaderBase(BaseModel):
    leader_name: str
    alias_name: str | None = None
    position: str | None = None
    party: str | None = None
    epic_no: str | None = None
    aadhaar_number: str | None = None
    mobile_number: str | None = None
    village_name: str
    mandal_name: str
    date_joined: date | None = None
    status: str = "active"
    remarks: str | None = None

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: str | None) -> str | None:
        return validate_epic_no(v)


class LocalLeaderCreate(LocalLeaderBase):
    photo_url: str | None = None


class LocalLeaderUpdate(LocalLeaderCreate):
    pass


class LocalLeaderOut(ORMModel):
    id: int
    leader_name: str
    alias_name: str | None
    position: str | None
    party: str | None
    voter_id: int | None
    epic_no: str | None
    aadhaar_masked: str | None = None
    mobile_number: str | None
    village_id: int
    mandal_id: int
    date_joined: date | None
    status: str
    photo_url: str | None
    remarks: str | None
