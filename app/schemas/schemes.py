"""Government Schemes page (frontend: GovernmentSchemes.jsx / SchemeModals.jsx).

The Add/Edit form sends: name, department, frequency, benefit,
amount_per_beneficiary, status ("Active"/"Inactive"), extra_details
(comma-separated, shown as tags), other_spellings, description.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchemeCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=150)
    telugu_name: str | None = Field(default=None, max_length=150)
    department: str | None = Field(default=None, max_length=150)
    frequency: str | None = Field(default=None, max_length=50)
    benefit: str | None = Field(default=None, max_length=200)
    amount_per_beneficiary: Decimal | None = Field(default=None, ge=0)
    status: str = "Active"
    extra_details: str | None = None
    other_spellings: str | None = None
    description: str | None = None

    @field_validator(
        "telugu_name", "department", "frequency", "benefit", "extra_details", "other_spellings", "description",
        "amount_per_beneficiary",
        mode="before",
    )
    @classmethod
    def _blank(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        text = str(v or "Active").strip().lower()
        if text not in ("active", "inactive"):
            raise ValueError("status must be Active or Inactive")
        return text.capitalize()


class SchemeUpdate(SchemeCreate):
    pass
