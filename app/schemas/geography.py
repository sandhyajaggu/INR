from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

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


BOOTH_STATUS_PATTERN = "^(On Time|Delayed)$"


class BoothCreate(BaseModel):
    booth_number: str = Field(min_length=1, max_length=20)
    booth_name: str | None = None
    village_name: str
    mandal_name: str
    location_address: str | None = None
    total_voters: int = Field(default=0, ge=0)
    votes_polled: int = Field(default=0, ge=0)
    booth_officer_name: str | None = None
    booth_officer_mobile: str | None = None
    tdp_votes: int = Field(default=0, ge=0)
    ysp_votes: int = Field(default=0, ge=0)
    janasena_votes: int = Field(default=0, ge=0)
    congress_votes: int = Field(default=0, ge=0)
    status: str | None = Field(default=None, pattern=BOOTH_STATUS_PATTERN)

    @field_validator("booth_number", "village_name", "mandal_name", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("booth_officer_mobile", mode="before")
    @classmethod
    def _validate_mobile(cls, v: object) -> str | None:
        return validate_mobile_number(v)

    @model_validator(mode="after")
    def _votes_within_registered(self) -> "BoothCreate":
        if self.votes_polled > self.total_voters:
            raise ValueError(
                f"votes_polled ({self.votes_polled}) cannot be more than total_voters ({self.total_voters})"
            )
        party_total = self.tdp_votes + self.ysp_votes + self.janasena_votes + self.congress_votes
        if party_total > self.total_voters:
            raise ValueError(
                f"TDP + YSP + Janasena + Congress votes ({party_total}) cannot be more than "
                f"total_voters ({self.total_voters})"
            )
        return self


class BoothUpdate(BoothCreate):
    pass


class BoothOut(BaseModel):
    """One Booth Summary table row. Mandal/village are returned by name only.

    pending_votes, voting_percentage and turnout are calculated from
    total_voters (Registered Votes) and votes_polled, not stored.
    """

    id: int
    booth_number: str
    booth_name: str | None
    mandal_name: str
    village_name: str
    location_address: str | None
    booth_officer_name: str | None
    booth_officer_mobile: str | None
    votes_polled: int
    total_voters: int
    pending_votes: int
    voting_percentage: float
    tdp_votes: int
    ysp_votes: int
    janasena_votes: int
    congress_votes: int
    turnout: float
    status: str | None
    created_at: datetime


class BoothSummary(BaseModel):
    total_booths: int
    completed: int
    completed_percentage: float
    pending: int
    pending_percentage: float
    delayed: int
    delayed_percentage: float


class MandalNameOut(BaseModel):
    name: str


class VillageNameOut(BaseModel):
    name: str
