"""Generic .xlsx row parser shared by every module's bulk-upload endpoint.

Reads the header row, maps each header to a snake_case key, and yields one
dict per data row tagged with its 1-based Excel row number under the
"_row_number" key (used in bulk-import error messages so an admin can find
the exact row to fix in their sheet). Blank rows are skipped.
"""

import re
from io import BytesIO

from fastapi import HTTPException, UploadFile, status
from openpyxl import load_workbook

# A sheet larger than this holds everything (raw rows, parsed models, and any
# row errors) in memory at once for the all-or-nothing validation pass, which
# has OOM-killed the service on real electoral-roll-sized sheets (200k+ rows).
# Failing fast here is cheap; ask the uploader to split the sheet instead.
MAX_ROWS_PER_SHEET = 50_000


def _normalize_header(value: object) -> str:
    return re.sub(r"\s+", "_", str(value).strip().lower())


def _normalize_sheet_name(value: str) -> str:
    return re.sub(r"[\s-]+", "_", value.strip().lower())


def _rows_from_iter(rows_iter, headers: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for excel_row_num, values in enumerate(rows_iter, start=2):
        if values is None or all(v is None for v in values):
            continue
        # Blank cells are omitted entirely (not passed through as None) so
        # each field's own Pydantic default applies — a bare `None` would
        # otherwise fail validation on non-Optional fields that have a
        # default, e.g. status: str = "pending" or is_new_voter: bool = False.
        row = {
            headers[i]: values[i]
            for i in range(len(headers))
            if i < len(values) and values[i] is not None
        }
        row["_row_number"] = excel_row_num
        rows.append(row)
    return rows


def _load_workbook_from_upload(contents: bytes):
    try:
        return load_workbook(filename=BytesIO(contents), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not read the Excel file") from exc


async def parse_excel_rows(file: UploadFile, required_columns: set[str]) -> list[dict[str, object]]:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only .xlsx files are supported")

    contents = await file.read()
    workbook = _load_workbook_from_upload(contents)

    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The sheet is empty")

    headers = [_normalize_header(h) for h in header_row if h is not None]
    missing = required_columns - set(headers)
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Missing required column(s): {', '.join(sorted(missing))}",
        )

    rows = _rows_from_iter(rows_iter, headers)
    if len(rows) > MAX_ROWS_PER_SHEET:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Sheet has {len(rows)} rows, which exceeds the {MAX_ROWS_PER_SHEET:,}-row limit per "
            "upload. Split it into smaller files (e.g. by mandal, or into batches) and upload each "
            "one separately.",
        )
    return rows


async def parse_excel_workbook(file: UploadFile) -> dict[str, list[dict[str, object]]]:
    """Parses every non-empty sheet tab in a multi-tab .xlsx workbook.

    Used by the combined all-schemes beneficiaries bulk-upload, where each
    sheet tab represents one scheme. Returns {normalized_sheet_name: rows},
    skipping sheets that are empty or header-only. Unlike parse_excel_rows,
    no required-columns check happens here — each sheet's rows are validated
    downstream against that scheme's own schema, since required fields differ
    per scheme.
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only .xlsx files are supported")

    contents = await file.read()
    workbook = _load_workbook_from_upload(contents)

    sheets: dict[str, list[dict[str, object]]] = {}
    for sheet in workbook.worksheets:
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            continue
        headers = [_normalize_header(h) for h in header_row if h is not None]
        if not headers:
            continue
        rows = _rows_from_iter(rows_iter, headers)
        if not rows:
            continue
        if len(rows) > MAX_ROWS_PER_SHEET:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Sheet '{sheet.title}' has {len(rows)} rows, which exceeds the "
                f"{MAX_ROWS_PER_SHEET:,}-row limit per upload. Split it into smaller files and "
                "upload each one separately.",
            )
        sheets[_normalize_sheet_name(sheet.title)] = rows

    return sheets


# --- Any-format uploads (.xlsx / .xls / .csv) --------------------------------
# The dashboard's upload dialogs accept ".xlsx, .xls, .csv" and their
# downloadable templates are CSV files with display headers ("EPIC No",
# "Full Name", ...). parse_upload_rows reads any of the three formats,
# normalizes headers to snake_case and maps template headers onto the
# schema's keys via `aliases`.


def _blank_cell(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def read_csv_table(contents: bytes) -> list[list[object]]:
    import csv
    import io

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel's "Save as CSV" on Windows writes the ANSI code page, not UTF-8.
        text = contents.decode("cp1252", errors="replace")
    return [[_blank_cell(v) for v in row] for row in csv.reader(io.StringIO(text))]


def read_xlsx_table(contents: bytes) -> list[list[object]]:
    sheet = _load_workbook_from_upload(contents).active
    return [[_blank_cell(v) for v in row] for row in sheet.iter_rows(values_only=True)]


def read_xls_table(contents: bytes) -> list[list[object]]:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=contents)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not read the Excel file") from exc
    sheet = book.sheet_by_index(0)
    table = []
    for r in range(sheet.nrows):
        row = []
        for value in sheet.row_values(r):
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            row.append(_blank_cell(value))
        table.append(row)
    return table


async def parse_upload_rows(
    file: UploadFile,
    required_columns: set[str],
    aliases: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Rows from an .xlsx / .xls / .csv upload, keyed by normalized (and aliased) header."""
    name = (file.filename or "").lower()
    contents = await file.read()
    if name.endswith((".xlsx", ".xlsm")):
        table = read_xlsx_table(contents)
    elif name.endswith(".xls"):
        table = read_xls_table(contents)
    elif name.endswith(".csv"):
        table = read_csv_table(contents)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only .xlsx, .xls and .csv files are supported")
    if not table:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The sheet is empty")
    header_row, *data_rows = table
    aliases = aliases or {}
    headers = []
    for h in header_row:
        if h is None:
            headers.append(f"_blank_{len(headers)}")
            continue
        key = _normalize_header(h)
        headers.append(aliases.get(key, key))
    missing = required_columns - set(headers)
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Missing required column(s): {', '.join(sorted(missing))}",
        )
    rows = _rows_from_iter(iter(data_rows), headers)
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The sheet has no data rows below the header")
    if len(rows) > MAX_ROWS_PER_SHEET:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Sheet has {len(rows)} rows, which exceeds the {MAX_ROWS_PER_SHEET:,}-row limit per "
            "upload. Split it into smaller files and upload each one separately.",
        )
    return rows
