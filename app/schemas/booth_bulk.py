"""Row shape for the booths bulk-upload sheet (Super Admin → Booths → Upload).

Column headers match the Upload Booth Data popup ("Booth No", "In Charge",
...), normalized to snake_case by the sheet parser. Every column is
mandatory. Mandal/Village are given by name and resolved to IDs by the
import service.
"""

from pydantic import BaseModel, Field, field_validator, model_validator

BOOTH_STATUSES = ("On Time", "Delayed")

# Sheet header (as shown in the template) -> normalized key.
BOOTH_SHEET_COLUMNS: dict[str, str] = {
    "Booth No": "booth_no",
    "In Charge": "in_charge",
    "Mandal": "mandal",
    "Village": "village",
    "Registered Votes": "registered_votes",
    "TDP": "tdp",
    "YSP": "ysp",
    "Janasena": "janasena",
    "Status": "status",
}
BOOTH_COLUMN_LABELS = {key: label for label, key in BOOTH_SHEET_COLUMNS.items()}


class BoothBulkRow(BaseModel):
    booth_no: str = Field(max_length=20)
    in_charge: str = Field(min_length=1, max_length=150)
    mandal: str
    village: str
    registered_votes: int = Field(ge=0)
    tdp: int = Field(ge=0)
    ysp: int = Field(ge=0)
    janasena: int = Field(ge=0)
    status: str

    @field_validator("booth_no", mode="before")
    @classmethod
    def _booth_no_to_str(cls, v: object) -> object:
        # Excel stores a typed booth number like 12 as a number (12 or 12.0);
        # booths.booth_number is text, so compare/store it as "12".
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, int):
            return str(v)
        return v.strip() if isinstance(v, str) else v

    @field_validator("in_charge", "mandal", "village", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def _canonical_status(cls, v: object) -> str:
        text = " ".join(str(v).split()).lower()
        for status in BOOTH_STATUSES:
            if status.lower() == text:
                return status
        raise ValueError(f"must be 'On Time' or 'Delayed', got '{v}'")

    @model_validator(mode="after")
    def _party_votes_within_registered(self) -> "BoothBulkRow":
        party_total = self.tdp + self.ysp + self.janasena
        if party_total > self.registered_votes:
            raise ValueError(
                f"TDP + YSP + Janasena ({party_total}) is more than Registered Votes ({self.registered_votes})"
            )
        return self
