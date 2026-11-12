"""Telugu content for the public website.

Content records (events, development works, media) keep their Telugu text in a
JSONB column `te` = {field: telugu text}, keyed by the field name the API
returns ("title", "venue", ...).

Dashboard side
    Create / edit forms send `<field>_te` next to the English field
    (`title_te`, `venue_te`, ...). Only keys actually sent change; "" clears one.
    Rows always carry `<field>_te` so edit forms can show it.

Public side
    `?lang=te` swaps each text field to its Telugu value, falls back to English
    when no Telugu was entered, and keeps the English under `<field>_en`.
    Codes the frontend logic depends on (status, type, category, ids, dates,
    urls) are never swapped.
"""

from collections.abc import Iterable
from typing import Annotated, Any, Literal

from fastapi import Query
from pydantic import BaseModel

Lang = Literal["en", "te"]
LangQuery = Annotated[
    Lang, Query(description="te = Telugu text where entered (falls back to English); English kept in <field>_en")
]


def te_updates(payload: BaseModel, keys: Iterable[str]) -> dict[str, str | None]:
    """{field: telugu} for every `<field>_te` the client actually sent ("" / null clears it)."""
    out: dict[str, str | None] = {}
    for key in keys:
        attr = f"{key}_te"
        if attr in payload.model_fields_set:
            value = getattr(payload, attr, None)
            value = value.strip() if isinstance(value, str) else value
            out[key] = value or None
    return out


def apply_te(obj: Any, updates: dict[str, str | None]) -> None:
    """Merge te_updates() into obj.te (a new dict, so SQLAlchemy sees the change)."""
    if not updates:
        return
    te = dict(obj.te or {})
    for key, value in updates.items():
        if value:
            te[key] = value
        else:
            te.pop(key, None)
    obj.te = te


def te_keys(te: dict | None, keys: Iterable[str]) -> dict[str, str | None]:
    """`<field>_te` keys for a row."""
    te = te or {}
    return {f"{key}_te": te.get(key) for key in keys}


def localize(row: dict[str, Any], lang: str | None, keys: Iterable[str]) -> dict[str, Any]:
    """lang="te": row[field] = Telugu (if entered), English kept as row[field_en]. Other langs: unchanged."""
    if lang != "te":
        return row
    for key in keys:
        if key in row:
            row[f"{key}_en"] = row[key]
            telugu = row.get(f"{key}_te")
            if telugu:
                row[key] = telugu
    return row


def localize_all(rows: list[dict[str, Any]], lang: str | None, keys: Iterable[str]) -> list[dict[str, Any]]:
    keys = list(keys)
    return [localize(r, lang, keys) for r in rows]
