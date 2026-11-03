"""Display IDs that match the frontend's record IDs.

The dashboard shows and passes around IDs like "U-101", "FAM-5119" or
"GO-107". The database keeps plain integer primary keys; these helpers turn
a primary key into the prefixed form for responses, and accept either form
("FAM-5119" or "5119") back in path parameters.
"""

import re

from fastapi import HTTPException, status

_TRAILING_DIGITS = re.compile(r"(\d+)$")


def format_id(prefix: str, pk: int | None) -> str | None:
    if pk is None:
        return None
    return f"{prefix}-{pk}"


def parse_id(value: str | int, *, label: str = "record") -> int:
    """Return the integer primary key from "PREFIX-123", "PREFIX-2026-123" or "123"."""
    if isinstance(value, int):
        return value
    match = _TRAILING_DIGITS.search(str(value).strip())
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return int(match.group(1))
