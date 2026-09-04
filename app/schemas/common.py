import re
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

EPIC_NO_PATTERN = re.compile(r"^[A-Z]{3}[0-9]{7}$")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def validate_epic_no(value: object) -> str | None:
    """Shared EPIC-number format check.

    Applied everywhere epic_no is stored — including tables with no hard FK
    to voters (beneficiaries, surveys, notes_followups, local_leaders,
    janata_darbar_visits, contact_messages) — per the spec: the format must
    still be validated even when the voter doesn't exist yet. Normalizes to
    uppercase so downstream lookups by epic_no are case-insensitive.

    Accepts non-string input (e.g. a bulk-Excel-upload cell that got read
    back as an int/float because the column wasn't formatted as text) by
    coercing to str first, so a malformed cell fails the format check below
    like any other bad value instead of raising an uncaught AttributeError.
    """
    if value is None or value == "":
        return None
    normalized = str(value).strip().upper()
    if not EPIC_NO_PATTERN.match(normalized):
        raise ValueError("epic_no must be 3 letters followed by 7 digits, e.g. ABC1234567")
    return normalized


GENDER_ALIASES = {"MALE": "Male", "M": "Male", "FEMALE": "Female", "F": "Female", "OTHER": "Other", "O": "Other"}


def normalize_gender(value: object) -> object:
    """Normalizes real-world gender-column spellings from bulk-upload sheets.

    Electoral-roll sheets commonly record gender as a single letter (M/F/O)
    or with inconsistent casing/whitespace (e.g. "male ", "FEMALE") instead
    of the canonical Male/Female/Other the app stores. An unrecognized value
    passes through unchanged so the existing pattern validator still rejects
    genuinely bad data.
    """
    if not isinstance(value, str):
        return value
    return GENDER_ALIASES.get(value.strip().upper(), value)


def coerce_excel_cell_to_str(value: object) -> object:
    """Coerces a bulk-Excel-upload cell read back as int/float to a plain string.

    openpyxl reads a numeric-looking cell (e.g. a house number typed as a
    bare number instead of formatted as text) back as an int/float, which
    pydantic's plain `str` fields reject outright ("Input should be a valid
    string") instead of validating the format underneath. Whole-number
    floats drop the trailing ".0" (openpyxl returns a float for any numeric
    cell, even one holding a whole number). None/str/anything else passes
    through unchanged for normal validation to handle.
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    return value
