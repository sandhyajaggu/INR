"""Booths bulk upload (.xlsx / .xls / .csv): validation and upsert.

All-or-nothing like the voters import: every row is validated first
(required fields, numbers, mobile format, resolvable mandal/village, no
duplicate booth within the file). If any row fails, nothing is written.
Otherwise a row whose (mandal, booth number) already exists updates that
booth, and every other row adds a new booth.
"""

from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geography import Booth, Mandal, Village
from app.schemas.booth_bulk import BOOTH_COLUMN_LABELS, BOOTH_HEADER_ALIASES, BoothBulkRow
from app.schemas.bulk_import import BulkImportResult, BulkImportRowError
from app.services.activity_service import log_activity
from app.services.bulk_template_service import (
    TemplateColumn,
    TemplateSheet,
    build_single_sheet_template,
    mandal_names,
)
from app.services.excel_import_service import parse_upload_rows
from app.services.geography_service import load_geography_maps

TEMPLATE_EXAMPLE_ROWS = [
    ["256", "ZPH School Daida", 1050, "Kandukur", "Kandukur (Rural)", "Ramesh Kumar", "9876543210", "9123456780"],
]

REQUIRED_KEYS = {"booth_no", "name", "voters", "mandal", "village", "agent_name", "agent_mobile"}


async def parse_booth_upload(file: UploadFile) -> list[dict[str, object]]:
    return await parse_upload_rows(file, required_columns=REQUIRED_KEYS, aliases=BOOTH_HEADER_ALIASES)


def _format_validation_error(exc: ValidationError) -> str:
    messages = []
    for err in exc.errors():
        label = BOOTH_COLUMN_LABELS.get(str(err["loc"][0]), str(err["loc"][0])) if err["loc"] else ""
        msg = err["msg"].removeprefix("Value error, ")
        if err["type"] == "missing":
            msg = "is required"
        elif err["type"].startswith("int_"):
            msg = f"must be a whole number, got '{err['input']}'"
        messages.append(f"{label} {msg}".strip())
    return "; ".join(messages)


async def bulk_import_booths(db: AsyncSession, rows: list[dict], actor_id: int) -> BulkImportResult:
    errors: list[BulkImportRowError] = []
    parsed_rows: list[tuple[int, BoothBulkRow]] = []

    for raw in rows:
        row_num = raw.get("_row_number")
        try:
            parsed_rows.append((row_num, BoothBulkRow.model_validate(raw)))
        except ValidationError as exc:
            booth_hint = raw.get("booth_no")
            prefix = f"Booth No '{booth_hint}': " if booth_hint is not None else ""
            errors.append(BulkImportRowError(row=row_num, reason=prefix + _format_validation_error(exc)))

    mandal_map, village_map, _ = await load_geography_maps(db)
    resolved: list[tuple[BoothBulkRow, int, int]] = []
    first_seen: dict[tuple[int, str], int] = {}
    for row_num, parsed in parsed_rows:
        prefix = f"Booth No '{parsed.booth_no}': "
        mandal_id = mandal_map.get(parsed.mandal.lower())
        if mandal_id is None:
            errors.append(BulkImportRowError(row=row_num, reason=f"{prefix}Unknown mandal '{parsed.mandal}'"))
            continue
        village_id = village_map.get((mandal_id, parsed.village.lower()))
        if village_id is None:
            errors.append(
                BulkImportRowError(
                    row=row_num, reason=f"{prefix}Unknown village '{parsed.village}' in mandal '{parsed.mandal}'"
                )
            )
            continue
        key = (mandal_id, parsed.booth_no)
        if key in first_seen:
            errors.append(
                BulkImportRowError(
                    row=row_num,
                    reason=f"{prefix}Duplicate booth in mandal '{parsed.mandal}' (first seen on row {first_seen[key]})",
                )
            )
            continue
        first_seen[key] = row_num
        resolved.append((parsed, mandal_id, village_id))

    if errors:
        errors.sort(key=lambda e: e.row)
        return BulkImportResult(inserted=0, errors=errors)

    # The booths table is small (a few hundred rows per constituency).
    existing = {
        (b.mandal_id, b.booth_number.strip()): b for b in (await db.execute(select(Booth))).scalars().all()
    }
    new_booths = []
    updated_count = 0
    for parsed, mandal_id, village_id in resolved:
        values = {
            "village_id": village_id,
            "booth_name": parsed.name,
            "total_voters": parsed.voters,
            "booth_officer_name": parsed.agent_name,
            "booth_officer_mobile": parsed.agent_mobile,
            "agent_alt_mobile": parsed.agent_alt_mobile,
        }
        booth = existing.get((mandal_id, parsed.booth_no))
        if booth is not None:
            for field, value in values.items():
                setattr(booth, field, value)
            updated_count += 1
        else:
            new_booths.append(Booth(booth_number=parsed.booth_no, mandal_id=mandal_id, **values))

    db.add_all(new_booths)
    await db.flush()
    await log_activity(
        db,
        actor_id=actor_id,
        action_type="booth_bulk_imported",
        module="booths",
        reference_id=None,
        description=f"Bulk import: {len(new_booths)} booths added, {updated_count} updated",
    )
    await db.commit()
    return BulkImportResult(inserted=len(new_booths), updated=updated_count, errors=[])


async def build_booth_template(db: AsyncSession) -> bytes:
    """The upload template, pre-filled with every current booth (edit and upload back)."""
    stmt = (
        select(Booth, Mandal.name, Village.name)
        .join(Mandal, Mandal.id == Booth.mandal_id)
        .join(Village, Village.id == Booth.village_id)
        .order_by(Mandal.name, Booth.booth_number)
    )
    booths = [
        [b.booth_number, b.booth_name, b.total_voters, mandal, village, b.booth_officer_name,
         b.booth_officer_mobile, b.agent_alt_mobile]
        for b, mandal, village in (await db.execute(stmt)).all()
    ]
    spec = TemplateSheet("Booths", booth_template_columns(await mandal_names(db)), booths or TEMPLATE_EXAMPLE_ROWS)
    notes = [
        "Columns marked required must be filled; hover a header to see its rule.",
        "This file lists the current booths: edit them and upload the file back. A row whose Mandal + Booth No "
        "already exists updates that booth; new rows add booths.",
        "Accepted files: .xlsx, .xls or .csv.",
        "If any row has a problem, nothing is saved and every problem is listed with its row number.",
    ]
    return build_single_sheet_template(spec, notes)


def booth_template_columns(mandals: list[str]) -> list[TemplateColumn]:
    return [
        TemplateColumn("Booth No", True, "Booth number as printed, e.g. 256", as_text=True),
        TemplateColumn("Polling Station", True, "Polling station name"),
        TemplateColumn("Voters", True, "Whole number of voters in the booth"),
        TemplateColumn("Mandal", True, "One of the mandals in the dropdown", choices=mandals or None),
        TemplateColumn("Village", True, "Village in that mandal"),
        TemplateColumn("Agent Name", True, "Booth agent name"),
        TemplateColumn("Agent Mobile", True, "10 digits, starts with 6-9", as_text=True),
        TemplateColumn("Agent Alt Mobile", False, "10 digits, starts with 6-9", as_text=True),
    ]
