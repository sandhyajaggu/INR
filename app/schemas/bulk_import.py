"""Shared response shapes for every module's Excel bulk-upload endpoint.

One generic result shape is reused across voters, beneficiaries, and
development works so the frontend handles bulk-upload responses uniformly.
"""

from pydantic import BaseModel


class BulkImportRowError(BaseModel):
    row: int
    epic_no: str | None = None
    reason: str


class BulkImportResult(BaseModel):
    inserted: int
    errors: list[BulkImportRowError] = []
