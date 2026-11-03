"""Voters (frontend: Voters.js, AddVoterModal.jsx, UploadVotersModal.jsx).

The Add/Edit Voter form sends:
    epic_no, name, relation_type, relation_name, gender ("M"/"F"/"Third gender"),
    age, religion, caste_category, mandal, village, booth_no ("#256"),
    mobile, alt_mobile, voted_last_election ("Yes"/"No"), is_new_voter
    ("Yes"/"No"), status ("Verified"/"Pending"), dob
The older field names (mandal_name, village_name, booth_id, gender
"Male"/"Female"/"Other", booleans) are still accepted.
"""

import re
from datetime import date, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.schemas.common import coerce_excel_cell_to_str, validate_epic_no
from app.services.voter_profile import from_yes_no, gender_to_db, strip_booth_label

MOBILE_PATTERN = r"^[6-9][0-9]{9}$"
RELATION_TYPES = ("S/o", "W/o", "D/o", "H/o", "C/o")
RELIGIONS = ("Hindu", "Muslim", "Christian", "Sikh", "Buddhist", "Jain", "Other")
CASTE_CATEGORIES = ("OC", "BC-A", "BC-B", "BC-C", "BC-D", "BC-E", "SC", "ST", "Minority", "Other")


def _blank(value: object) -> object:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _check_mobile(value: str | None, label: str) -> str | None:
    if value and not re.match(MOBILE_PATTERN, value):
        raise ValueError(f"{label} must be a valid 10-digit Indian mobile number")
    return value


def _parse_dob(value: object) -> object:
    """Accepts YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, or an Excel date."""
    value = _blank(value)
    if isinstance(value, datetime):
        return value.date()
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", text)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return text[:10]


class VoterFields(BaseModel):
    epic_no: str = Field(description="EPIC/Voter ID, e.g. ABC1234567")
    name: str = Field(min_length=1, max_length=150)
    relation_type: str | None = None
    relation_name: str | None = None
    gender: str | None = Field(default=None, description='"M", "F" or "Third gender"')
    age: int | None = Field(default=None, ge=0, le=130)
    religion: str | None = None
    caste_category: str | None = None
    mandal: str = Field(validation_alias=AliasChoices("mandal", "mandal_name"))
    village: str = Field(validation_alias=AliasChoices("village", "village_name"))
    booth_no: str | None = Field(default=None, validation_alias=AliasChoices("booth_no", "booth_number"))
    booth_id: int | None = None
    mobile: str | None = None
    alt_mobile: str | None = None
    voted_last_election: bool | None = None
    is_new_voter: bool = False
    status: str = Field(default="Pending", pattern="^(Verified|Pending)$")
    dob: date | None = None
    house_no: str | None = None
    aadhaar_number: str | None = Field(default=None, description="12-digit Aadhaar, plain text in request")
    photo_url: str | None = Field(default=None, validation_alias=AliasChoices("photo_url", "photo"))
    mobile_verified: bool | None = None

    @field_validator(
        "relation_type", "relation_name", "religion", "caste_category", "booth_no", "mobile", "alt_mobile",
        "house_no", "aadhaar_number", "photo_url", "gender",
        mode="before",
    )
    @classmethod
    def _clean_text(cls, v: object) -> object:
        return _blank(coerce_excel_cell_to_str(v))

    @field_validator("age", mode="before")
    @classmethod
    def _clean_age(cls, v: object) -> object:
        return _blank(v)

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: object) -> str:
        validated = validate_epic_no(v)
        if validated is None:
            raise ValueError("epic_no is required")
        return validated

    @field_validator("gender", mode="after")
    @classmethod
    def _gender(cls, v: str | None) -> str | None:
        g = gender_to_db(v)
        if g is not None and g not in ("Male", "Female", "Other"):
            raise ValueError('gender must be "M", "F" or "Third gender"')
        return g

    @field_validator("booth_no", mode="after")
    @classmethod
    def _booth(cls, v: str | None) -> str | None:
        return strip_booth_label(v)

    @field_validator("relation_type")
    @classmethod
    def _relation_type(cls, v: str | None) -> str | None:
        if v and v not in RELATION_TYPES:
            raise ValueError(f"relation_type must be one of {', '.join(RELATION_TYPES)}")
        return v

    @field_validator("voted_last_election", "is_new_voter", "mobile_verified", mode="before")
    @classmethod
    def _yes_no(cls, v: object) -> object:
        return from_yes_no(v)

    @field_validator("is_new_voter", mode="after")
    @classmethod
    def _new_voter_default(cls, v: bool | None) -> bool:
        return bool(v)

    @field_validator("dob", mode="before")
    @classmethod
    def _dob(cls, v: object) -> object:
        return _parse_dob(v)

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str | None) -> str | None:
        return _check_mobile(v, "mobile")

    @field_validator("alt_mobile")
    @classmethod
    def _alt_mobile(cls, v: str | None) -> str | None:
        return _check_mobile(v, "alt_mobile")

    @field_validator("aadhaar_number")
    @classmethod
    def _aadhaar(cls, v: str | None) -> str | None:
        if v and (not v.isdigit() or len(v) != 12):
            raise ValueError("aadhaar_number must be exactly 12 digits")
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> object:
        v = _blank(v)
        return "Pending" if v is None else str(v).strip().capitalize()


class VoterCreate(VoterFields):
    pass


class VoterUpdate(VoterFields):
    pass


class VoterBulkRow(VoterFields):
    """One row of the voters upload sheet (.xlsx / .xls / .csv).

    Same rules as the Add Voter form. Headers may be the frontend template's
    ("EPIC No", "Full Name", "Booth No", "Date of Birth", ...) or the older
    snake_case ones ("epic_no", "mandal_name", "booth_number", ...).
    """


# Upload-sheet header (normalized to snake_case) -> VoterFields key.
VOTER_HEADER_ALIASES: dict[str, str] = {
    "epic": "epic_no",
    "epic_number": "epic_no",
    "voter_id": "epic_no",
    "full_name": "name",
    "caste": "caste_category",
    "alternate_mobile": "alt_mobile",
    "alt_mobile_no": "alt_mobile",
    "date_of_birth": "dob",
    "mandal_name": "mandal",
    "village_name": "village",
    "booth_number": "booth_no",
    "new_voter": "is_new_voter",
}


class VoterRemoveRequest(BaseModel):
    reason: str = Field(default="Shifted", min_length=1, max_length=50)
    details: str | None = None


class VoterBulkRemoveRequest(VoterRemoveRequest):
    ids: list[int | str] = Field(min_length=1)


class MarkVotedRequest(BaseModel):
    party: str | None = Field(default=None, description="TDP / BJP / YSRCP / Janasena / Other")


class VoterStats(BaseModel):
    total: int
    male: int
    female: int
    thirdGender: int
    newVoters: int
    removed: int


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


VoterOut = dict[str, Any]
