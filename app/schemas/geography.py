from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, validate_mobile_number


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
    """Add/Edit Booth form (frontend: BoothModals.jsx BoothFormModal).

    booth_no, name (polling station), voters, mandal, village, agent_name and
    agent_mobile are required, as in the form; the rest are optional.
    """

    booth_no: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    name_te: str | None = Field(default=None, max_length=200)
    voters: int = Field(ge=0)
    mandal: str
    village: str
    agent_name: str = Field(min_length=1, max_length=150)
    agent_mobile: str
    agent_alt_mobile: str | None = None
    agent_photo: str | None = None
    location_address: str | None = None

    @field_validator("booth_no", mode="before")
    @classmethod
    def _booth_no(cls, v: object) -> object:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = str(int(v))
        return v.strip().lstrip("#").strip() if isinstance(v, str) else v

    @field_validator("name", "name_te", "mandal", "village", "agent_name", "agent_photo", "location_address", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("agent_mobile", mode="before")
    @classmethod
    def _agent_mobile(cls, v: object) -> str:
        value = validate_mobile_number(v)
        if value is None:
            raise ValueError("agent_mobile is required")
        return value

    @field_validator("agent_alt_mobile", mode="before")
    @classmethod
    def _alt_mobile(cls, v: object) -> str | None:
        return validate_mobile_number(v)


class BoothUpdate(BoothCreate):
    pass


class VoteToggleRequest(BaseModel):
    """toggleVoterVote(boothId, voterId, party, agentName)."""

    voter_id: int | str
    party: str = Field(default="TDP", pattern="^(TDP|BJP|YSRCP|Janasena|Other)$")
    agent_name: str | None = None


class MandalNameOut(BaseModel):
    name: str


class VillageNameOut(BaseModel):
    name: str
