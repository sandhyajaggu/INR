"""Shared response shapes for every module's Excel bulk-upload endpoint.

One generic result shape is reused across voters, beneficiaries, and
development works so the frontend handles bulk-upload responses uniformly.
"""

from pydantic import BaseModel

# A sheet that mostly fails validation can produce tens of thousands of row
# errors. Returning all of them as one JSON response has OOM-killed the
# service and frozen the browser trying to render it (Swagger UI included).
# Capping keeps the response small; the uploader fixes the shown errors,
# re-uploads, and sees the next batch.
MAX_REPORTED_ERRORS = 200


class BulkImportRowError(BaseModel):
    row: int
    epic_no: str | None = None
    reason: str


class BulkImportResult(BaseModel):
    inserted: int
    updated: int = 0
    errors: list[BulkImportRowError] = []


def capped_error_detail(errors: list[BulkImportRowError]) -> list[dict]:
    """Row-error list for an HTTPException detail, capped to MAX_REPORTED_ERRORS.

    Keeps the same list-of-dicts shape existing clients already parse
    (row/epic_no/reason) — just truncated, with one extra summary entry
    when there's more than fits.
    """
    detail = [e.model_dump() for e in errors[:MAX_REPORTED_ERRORS]]
    remaining = len(errors) - MAX_REPORTED_ERRORS
    if remaining > 0:
        detail.append(
            {
                "row": None,
                "epic_no": None,
                "reason": (
                    f"...and {remaining} more row error(s) not shown ({len(errors)} total). "
                    "Fix the errors above and re-upload to see the next batch."
                ),
            }
        )
    return detail
