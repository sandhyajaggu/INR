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
