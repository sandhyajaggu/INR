"""Settings page (frontend: SettingsPage.jsx, mockSettingsApi).

    GET /settings          getSettings()   -> {profile, profile_te, preferences, dropdowns}
    GET /public/settings   no login        -> {default_language: "en"|"te", telugu_default_website, profile, profile_te}
    PUT /settings          updateSettings({profile, profile_te, preferences, dropdowns}) -> {success, data}

profile:      constituency ("Kandukur (229)"), district, mla, office_phone, office_email, office_address
profile_te:   the same fields in Telugu
preferences:  language, sms_alert_citizen, daily_whatsapp_summary, agent_inactivity_alert,
              telugu_default_website, two_factor_staff
dropdowns:    {mandals: [{id: "m-<n>", value, telugu}], villages: {<mandal>: [{id: "v-<n>", value, telugu}]}}
              These are the real mandal / village lists used everywhere. Saving renames and adds
              entries; an entry left out is removed only if nothing uses it.
"""

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import DbSession, page_access
from app.core.telugu import LangQuery
from app.models.geography import Mandal, Village
from app.models.settings import AppSettings
from app.services.activity_service import log_activity

router = APIRouter(prefix="/settings", tags=["Settings"])
public_router = APIRouter(prefix="/public", tags=["Public"])

CanView = page_access("settings", "view")
CanEdit = page_access("settings", "edit")

DEFAULT_PREFERENCES = {
    "language": "English",
    "sms_alert_citizen": True,
    "daily_whatsapp_summary": True,
    "agent_inactivity_alert": True,
    "telugu_default_website": False,
    "two_factor_staff": True,
}
PROFILE_KEYS = ("constituency", "district", "mla", "office_phone", "office_email", "office_address")


class Profile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    constituency: str | None = None
    district: str | None = None
    mla: str | None = None
    office_phone: str | None = Field(default=None, max_length=150)
    office_email: str | None = None
    office_address: str | None = None


class DropdownItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | int | None = None
    value: str = Field(min_length=1, max_length=150)
    telugu: str | None = None


class Dropdowns(BaseModel):
    mandals: list[DropdownItem] = []
    villages: dict[str, list[DropdownItem]] = {}


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile: Profile | None = None
    profile_te: Profile | None = None
    preferences: dict[str, Any] | None = None
    dropdowns: Dropdowns | None = None


async def _settings_row(db) -> AppSettings:
    row = (await db.execute(select(AppSettings).order_by(AppSettings.id).limit(1))).scalar_one_or_none()
    if row is None:
        row = AppSettings()
        db.add(row)
        await db.flush()
    return row


def _profile(row: AppSettings) -> dict[str, Any]:
    constituency = row.constituency_name or ""
    if row.constituency_no and f"({row.constituency_no})" not in constituency:
        constituency = f"{constituency} ({row.constituency_no})".strip()
    return {
        "constituency": constituency or None,
        "district": row.district,
        "mla": row.current_mla,
        "office_phone": row.contact_phone,
        "office_email": row.contact_email,
        "office_address": row.office_address,
    }


def _apply_profile(row: AppSettings, profile: Profile) -> None:
    data = profile.model_dump(exclude_unset=True)
    if "constituency" in data:
        text = (data["constituency"] or "").strip()
        m = re.match(r"^(.*?)\s*\((\w+)\)\s*$", text)
        row.constituency_name, row.constituency_no = (m.group(1), m.group(2)) if m else (text or None, row.constituency_no)
    mapping = {"district": "district", "mla": "current_mla", "office_phone": "contact_phone",
               "office_email": "contact_email", "office_address": "office_address"}
    for key, column in mapping.items():
        if key in data:
            setattr(row, column, data[key])


async def _dropdowns(db) -> dict[str, Any]:
    mandals = (await db.execute(select(Mandal).order_by(Mandal.id))).scalars().all()
    villages = (await db.execute(select(Village).order_by(Village.mandal_id, Village.name))).scalars().all()
    by_mandal: dict[str, list[dict[str, Any]]] = {m.name: [] for m in mandals}
    names = {m.id: m.name for m in mandals}
    for v in villages:
        by_mandal.setdefault(names.get(v.mandal_id, ""), []).append({"id": f"v-{v.id}", "value": v.name, "telugu": v.name_te or ""})
    return {
        "mandals": [{"id": f"m-{m.id}", "value": m.name, "telugu": m.name_te or ""} for m in mandals],
        "villages": by_mandal,
    }


def _db_id(item_id: str | int | None) -> int | None:
    digits = re.sub(r"\D", "", str(item_id or ""))
    return int(digits) if digits and len(digits) < 10 else None  # frontend-made ids are Date.now() values


async def _sync_dropdowns(db, dropdowns: Dropdowns) -> list[str]:
    """Rename / add mandals and villages; remove ones left out when unused. Returns notes for skipped removals."""
    notes: list[str] = []
    existing_mandals = {m.id: m for m in (await db.execute(select(Mandal))).scalars().all()}
    kept_mandals: set[int] = set()
    mandal_by_name: dict[str, Mandal] = {}
    for item in dropdowns.mandals:
        m = existing_mandals.get(_db_id(item.id))
        if m is None:
            m = next((x for x in existing_mandals.values() if x.name.lower() == item.value.strip().lower()), None)
        if m is None:
            m = Mandal(name=item.value.strip())
            db.add(m)
            await db.flush()
            existing_mandals[m.id] = m
        m.name, m.name_te = item.value.strip(), (item.telugu or None)
        kept_mandals.add(m.id)
        mandal_by_name[m.name.lower()] = m

    existing_villages = {v.id: v for v in (await db.execute(select(Village))).scalars().all()}
    kept_villages: set[int] = set()
    for mandal_name, items in dropdowns.villages.items():
        mandal = mandal_by_name.get(mandal_name.strip().lower())
        if mandal is None:
            continue
        for item in items:
            v = existing_villages.get(_db_id(item.id))
            if v is None:
                v = next((x for x in existing_villages.values()
                          if x.mandal_id == mandal.id and x.name.lower() == item.value.strip().lower()), None)
            if v is None:
                v = Village(mandal_id=mandal.id, name=item.value.strip())
                db.add(v)
                await db.flush()
                existing_villages[v.id] = v
            v.name, v.name_te = item.value.strip(), (item.telugu or None)
            kept_villages.add(v.id)

    # Only touch villages of mandals the payload actually listed villages for.
    listed_mandal_ids = {mandal_by_name[n.strip().lower()].id for n in dropdowns.villages if n.strip().lower() in mandal_by_name}
    for v in list(existing_villages.values()):
        if v.id not in kept_villages and v.mandal_id in listed_mandal_ids:
            try:
                async with db.begin_nested():
                    await db.delete(v)
            except IntegrityError:
                notes.append(f"Village '{v.name}' is in use and was kept")
    if dropdowns.mandals:
        for m in list(existing_mandals.values()):
            if m.id not in kept_mandals:
                try:
                    async with db.begin_nested():
                        await db.delete(m)
                except IntegrityError:
                    notes.append(f"Mandal '{m.name}' is in use and was kept")
    return notes


async def settings_payload(db) -> dict[str, Any]:
    row = await _settings_row(db)
    return {
        "profile": _profile(row),
        "profile_te": {k: (row.profile_te or {}).get(k) for k in PROFILE_KEYS},
        "preferences": {**DEFAULT_PREFERENCES, **(row.preferences or {})},
        "dropdowns": await _dropdowns(db),
    }


@public_router.get("/settings", summary="Public website settings: default UI language + office profile (unauthenticated)")
async def get_public_settings(db: DbSession, lang: LangQuery | None = None) -> dict[str, Any]:
    """What the public site needs before anyone logs in.

    default_language is "te" when Settings > "Telugu default website" is on, else "en"
    (i18next language codes, ready for i18n.changeLanguage()). Only public office
    details are returned; dropdowns and staff preferences stay behind /settings.

    ?lang=te: `profile` holds the Telugu values (English where none entered), and
    `profile_en` the English ones.
    """
    row = (await db.execute(select(AppSettings).order_by(AppSettings.id).limit(1))).scalar_one_or_none()
    prefs = {**DEFAULT_PREFERENCES, **((row.preferences if row else None) or {})}
    telugu = bool(prefs.get("telugu_default_website"))
    profile = _profile(row) if row else {k: None for k in PROFILE_KEYS}
    profile_te = {k: ((row.profile_te if row else None) or {}).get(k) for k in PROFILE_KEYS}
    out: dict[str, Any] = {
        "default_language": "te" if telugu else "en",
        "telugu_default_website": telugu,
        "profile": profile,
        "profile_te": profile_te,
    }
    if lang == "te":
        out["profile_en"] = profile
        out["profile"] = {k: profile_te.get(k) or profile.get(k) for k in PROFILE_KEYS}
    return out


@router.get("", summary="getSettings()")
async def get_settings(db: DbSession, current_user: CanView) -> dict[str, Any]:
    data = await settings_payload(db)
    await db.commit()
    return data


@router.put("", summary="updateSettings(data)")
async def update_settings(payload: SettingsUpdate, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    row = await _settings_row(db)
    if payload.profile is not None:
        _apply_profile(row, payload.profile)
    if payload.profile_te is not None:
        row.profile_te = {**(row.profile_te or {}), **payload.profile_te.model_dump(exclude_unset=True)}
    if payload.preferences is not None:
        allowed = {k: v for k, v in payload.preferences.items() if k in DEFAULT_PREFERENCES}
        row.preferences = {**DEFAULT_PREFERENCES, **(row.preferences or {}), **allowed}
    notes: list[str] = []
    if payload.dropdowns is not None:
        notes = await _sync_dropdowns(db, payload.dropdowns)
    await log_activity(db, actor_id=current_user.id, action_type="settings_updated", module="Settings",
                       reference_id=None, description="Updated settings")
    await db.commit()
    return {"success": True, "notes": notes, "data": await settings_payload(db)}


