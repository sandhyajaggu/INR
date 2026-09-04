import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, coerce_excel_cell_to_str, normalize_gender, validate_epic_no

MOBILE_PATTERN = r"^[6-9][0-9]{9}$"


class VoterBase(BaseModel):
    epic_no: str = Field(description="EPIC/Voter ID, e.g. ABC1234567")
    name: str
    relation_name: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = Field(default=None, pattern="^(Male|Female|Other)$")
    mobile: str | None = None
    aadhaar_number: str | None = Field(default=None, description="12-digit Aadhaar, plain text in request")
    house_no: str | None = None
    village_name: str
    mandal_name: str
    booth_id: int | None = None
    voted_last_election: bool | None = None
    is_new_voter: bool = False

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: str) -> str:
        validated = validate_epic_no(v)
        if validated is None:
            raise ValueError("epic_no is required")
        return validated

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str | None) -> str | None:
        if v and not re.match(MOBILE_PATTERN, v):
            raise ValueError("mobile must be a valid 10-digit Indian mobile number")
        return v

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: str | None) -> str | None:
        if v and not v.isdigit():
            raise ValueError("aadhaar_number must be 12 digits")
        if v and len(v) != 12:
            raise ValueError("aadhaar_number must be exactly 12 digits")
        return v


class VoterCreate(VoterBase):
    photo_url: str | None = None


class VoterUpdate(VoterBase):
    photo_url: str | None = None


class VoterOut(ORMModel):
    id: int
    epic_no: str
    name: str
    relation_name: str | None
    age: int | None
    gender: str | None
    mobile: str | None
    aadhaar_masked: str | None = None
    house_no: str | None
    village_id: int
    mandal_id: int
    booth_id: int | None
    voted_last_election: bool | None
    is_new_voter: bool
    photo_url: str | None
    created_at: datetime
    updated_at: datetime


class MandalVoterSummary(BaseModel):
    mandal_id: int
    mandal_name: str
    male_voters: int
    female_voters: int
    total_voters: int
    pct_of_total: float | None


class GenderDistribution(BaseModel):
    gender: str | None
    total: int


class VoterBulkRow(BaseModel):
    """One row of a voters bulk-upload Excel sheet.

    Same field rules as VoterCreate, except booth is given as the printed
    booth_number (resolved to booth_id by the bulk-import service) instead
    of the internal booth_id — spreadsheets carry human-readable booth
    numbers, not internal IDs.
    """

    epic_no: str
    name: str
    relation_name: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = Field(default=None, pattern="^(Male|Female|Other)$")
    mobile: str | None = None
    aadhaar_number: str | None = None
    house_no: str | None = None
    mandal_name: str
    village_name: str
    booth_number: str | None = None
    voted_last_election: bool | None = None
    is_new_voter: bool = False

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: str) -> str:
        validated = validate_epic_no(v)
        if validated is None:
            raise ValueError("epic_no is required")
        return validated

    @field_validator(
        "name", "relation_name", "house_no", "mobile", "mandal_name", "village_name", "booth_number",
        mode="before",
    )
    @classmethod
    def _coerce_numeric_cells(cls, v: object) -> object:
        return coerce_excel_cell_to_str(v)

    @field_validator("gender", mode="before")
    @classmethod
    def _normalize_gender(cls, v: object) -> object:
        return normalize_gender(v)

    @field_validator("mobile")
    @classmethod
    def _validate_mobile(cls, v: str | None) -> str | None:
        if v and not re.match(MOBILE_PATTERN, v):
            raise ValueError("mobile must be a valid 10-digit Indian mobile number")
        return v

    @field_validator("aadhaar_number")
    @classmethod
    def _validate_aadhaar(cls, v: str | None) -> str | None:
        if v and not v.isdigit():
            raise ValueError("aadhaar_number must be 12 digits")
        if v and len(v) != 12:
            raise ValueError("aadhaar_number must be exactly 12 digits")
        return v
