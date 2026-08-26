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


def validate_epic_no(value: str | None) -> str | None:
    """Shared EPIC-number format check.

    Applied everywhere epic_no is stored — including tables with no hard FK
    to voters (beneficiaries, surveys, notes_followups, local_leaders,
    janata_darbar_visits, contact_messages) — per the spec: the format must
    still be validated even when the voter doesn't exist yet. Normalizes to
    uppercase so downstream lookups by epic_no are case-insensitive.
    """
    if value is None or value == "":
        return None
    normalized = value.strip().upper()
    if not EPIC_NO_PATTERN.match(normalized):
        raise ValueError("epic_no must be 3 letters followed by 7 digits, e.g. ABC1234567")
    return normalized
