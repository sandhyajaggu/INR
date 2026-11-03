"""Booths page and Polling Day (frontend: Booths.jsx, BoothDetails.jsx, BoothModals.jsx,
PollingDay.jsx, PolingDayDetails.jsx).

Booth record shape (Booths page):
    id, booth_no, name, name_te, mandal, village, voters, agent_name,
    agent_initial, agent_mobile, agent_alt_mobile, agent_photo, last_login
    ("Never" or "30 Oct, 10:50 am"), days_since_login ("Never" or a number),
    status ("Not logged in" / "Active" / "Inactive"), mapped_pct,
    mobile_verified_pct, surveyed_pct, createdAt, updatedAt
Detail adds voter_list (frontend voter shape).

Polling Day record shape:
    id, booth_no, name, name_te, mandal, village, agent_name, voters,
    votes_polled, party_mix ("TDP 60% · YSRCP 30%" or "—"), leading
"""

import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import UserScope
from app.models.families import FamilyMember
from app.models.geography import Booth, Mandal, Village
from app.models.staff import StaffUser
from app.models.voters import Voter
from app.schemas.geography import BoothCreate
from app.services.geography_service import resolve_geography
from app.services.survey_service import surveyed_counts_by_booth
from app.services.voter_profile import format_marked_at, voter_rows

ACTIVE_AGENT_DAYS = 7


def _initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "A"
    return "".join(p[0] for p in parts[:2]).upper()


def _pct(part: int, whole: int) -> int | None:
    return round(part * 100 / whole) if whole else None


def _booths_query(scope: UserScope):
    stmt = (
        select(Booth, Mandal.name, Village.name)
        .join(Mandal, Mandal.id == Booth.mandal_id)
        .join(Village, Village.id == Booth.village_id)
    )
    return scope.apply(stmt, mandal_col=Booth.mandal_id, booth_col=Booth.id)


async def _voter_counts(db: AsyncSession, booth_ids: list[int]) -> dict[int, dict[str, int]]:
    """Per booth: voters, mapped to a family, mobile verified, voted, votes per party."""
    if not booth_ids:
        return {}
    mapped = select(FamilyMember.voter_id)
    stmt = (
        select(
            Voter.booth_id,
            func.count(),
            func.count().filter(Voter.id.in_(mapped)),
            func.count().filter(Voter.mobile_verified.is_(True), Voter.mobile.is_not(None)),
            func.count().filter(Voter.polling_status == "voted"),
        )
        .where(Voter.booth_id.in_(booth_ids), Voter.removed_at.is_(None))
        .group_by(Voter.booth_id)
    )
    counts = {
        row[0]: {"voters": row[1], "mapped": row[2], "verified": row[3], "voted": row[4], "parties": {}}
        for row in (await db.execute(stmt)).all()
    }
    party_stmt = (
        select(Voter.booth_id, Voter.voted_party, func.count())
        .where(Voter.booth_id.in_(booth_ids), Voter.removed_at.is_(None), Voter.polling_status == "voted")
        .group_by(Voter.booth_id, Voter.voted_party)
    )
    for booth_id, party, n in (await db.execute(party_stmt)).all():
        counts.setdefault(booth_id, {"voters": 0, "mapped": 0, "verified": 0, "voted": 0, "parties": {}})
        counts[booth_id]["parties"][party or "Not recorded"] = n
    return counts


async def _agent_logins(db: AsyncSession, mobiles: list[str]) -> dict[str, datetime | None]:
    mobiles = [m for m in mobiles if m]
    if not mobiles:
        return {}
    stmt = select(StaffUser.mobile, StaffUser.last_login_at).where(StaffUser.mobile.in_(mobiles))
    return {mobile: last for mobile, last in (await db.execute(stmt)).all()}


def _login_fields(last_login: datetime | None) -> dict[str, Any]:
    if last_login is None:
        return {"last_login": "Never", "days_since_login": "Never", "status": "Not logged in"}
    days = (datetime.now(timezone.utc) - last_login).days
    return {
        "last_login": format_marked_at(last_login),
        "days_since_login": days,
        "status": "Active" if days <= ACTIVE_AGENT_DAYS else "Inactive",
    }


def _party_mix(parties: dict[str, int], voted: int) -> tuple[str, str]:
    if not voted:
        return "—", "—"
    ranked = sorted(parties.items(), key=lambda kv: kv[1], reverse=True)
    mix = " · ".join(f"{p} {round(n * 100 / voted)}%" for p, n in ranked)
    leading = ranked[0][0] if ranked and ranked[0][0] != "Not recorded" else "—"
    return mix, leading


async def booth_rows(db: AsyncSession, rows: list[tuple[Booth, str, str]]) -> list[dict[str, Any]]:
    booth_ids = [b.id for b, _, _ in rows]
    counts = await _voter_counts(db, booth_ids)
    surveyed = await surveyed_counts_by_booth(db, booth_ids)
    logins = await _agent_logins(db, [b.booth_officer_mobile for b, _, _ in rows])
    out = []
    for booth, mandal, village in rows:
        c = counts.get(booth.id, {"voters": 0, "mapped": 0, "verified": 0, "voted": 0, "parties": {}})
        actual = c["voters"]
        out.append(
            {
                "id": str(booth.id),
                "booth_no": booth.booth_number,
                "name": booth.booth_name,
                "name_te": booth.booth_name_te,
                "mandal": mandal,
                "village": village,
                "voters": booth.total_voters or actual,
                "voters_in_roll": actual,
                "agent_name": booth.booth_officer_name,
                "agent_initial": _initials(booth.booth_officer_name),
                "agent_mobile": booth.booth_officer_mobile,
                "agent_alt_mobile": booth.agent_alt_mobile,
                "agent_photo": booth.agent_photo,
                **_login_fields(logins.get(booth.booth_officer_mobile)),
                "mapped_pct": _pct(c["mapped"], actual),
                "mobile_verified_pct": _pct(c["verified"], actual),
                "surveyed_pct": _pct(surveyed.get(booth.id, 0), actual),
                "votes_polled": c["voted"],
                "location_address": booth.location_address,
                "mandal_id": booth.mandal_id,
                "village_id": booth.village_id,
                "createdAt": booth.created_at,
                "updatedAt": booth.updated_at,
            }
        )
    return out


async def polling_rows(db: AsyncSession, rows: list[tuple[Booth, str, str]]) -> list[dict[str, Any]]:
    counts = await _voter_counts(db, [b.id for b, _, _ in rows])
    out = []
    for booth, mandal, village in rows:
        c = counts.get(booth.id, {"voters": 0, "voted": 0, "parties": {}})
        party_mix, leading = _party_mix(c["parties"], c["voted"])
        out.append(
            {
                "id": str(booth.id),
                "booth_no": booth.booth_number,
                "name": booth.booth_name,
                "name_te": booth.booth_name_te,
                "mandal": mandal,
                "village": village,
                "agent_name": booth.booth_officer_name,
                "voters": c["voters"],
                "votes_polled": c["voted"],
                "party_mix": party_mix,
                "leading": leading,
                "party_counts": {k: v for k, v in c["parties"].items()},
            }
        )
    return out


async def list_booth_rows(
    db: AsyncSession,
    scope: UserScope,
    *,
    q: str | None = None,
    mandal: str | None = None,
    village: str | None = None,
) -> list[tuple[Booth, str, str]]:
    stmt = _booths_query(scope)
    if mandal:
        stmt = stmt.where(func.lower(Mandal.name) == mandal.strip().lower())
    if village:
        stmt = stmt.where(func.lower(Village.name) == village.strip().lower())
    if q and q.strip():
        term = f"%{q.strip().lstrip('#')}%"
        stmt = stmt.where(
            or_(
                Booth.booth_number.ilike(term),
                Booth.booth_name.ilike(term),
                Booth.booth_officer_name.ilike(term),
                Mandal.name.ilike(term),
                Village.name.ilike(term),
            )
        )
    stmt = stmt.order_by(Mandal.name, func.length(Booth.booth_number), Booth.booth_number)
    return list((await db.execute(stmt)).all())


async def get_booth_row(db: AsyncSession, booth_id: str, scope: UserScope | None = None) -> tuple[Booth, str, str]:
    key = str(booth_id).strip()
    if not key.isdigit():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booth not found")
    stmt = _booths_query(scope or UserScope()).where(Booth.id == int(key))
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booth not found")
    return tuple(row)


async def booth_voter_list(db: AsyncSession, booth_id: int) -> list[dict[str, Any]]:
    stmt = select(Voter).where(Voter.booth_id == booth_id, Voter.removed_at.is_(None)).order_by(Voter.id)
    return await voter_rows(db, list((await db.execute(stmt)).scalars().all()))


async def _booth_values(db: AsyncSession, payload: BoothCreate, exclude_id: int | None) -> dict[str, Any]:
    data = payload.model_dump()
    mandal_id, village_id = await resolve_geography(db, mandal_name=data["mandal"], village_name=data["village"])
    duplicate = select(Booth.id).where(Booth.mandal_id == mandal_id, Booth.booth_number == data["booth_no"])
    if exclude_id is not None:
        duplicate = duplicate.where(Booth.id != exclude_id)
    if (await db.execute(duplicate)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Booth No '{data['booth_no']}' already exists in this mandal")
    return {
        "booth_number": data["booth_no"],
        "booth_name": data["name"],
        "booth_name_te": data.get("name_te"),
        "total_voters": data["voters"],
        "mandal_id": mandal_id,
        "village_id": village_id,
        "booth_officer_name": data["agent_name"],
        "booth_officer_mobile": data["agent_mobile"],
        "agent_alt_mobile": data.get("agent_alt_mobile"),
        "agent_photo": data.get("agent_photo"),
        "location_address": data.get("location_address"),
    }


async def create_booth(db: AsyncSession, payload: BoothCreate) -> Booth:
    booth = Booth(**await _booth_values(db, payload, exclude_id=None))
    db.add(booth)
    await db.flush()
    return booth


async def update_booth(db: AsyncSession, booth: Booth, payload: BoothCreate) -> None:
    for field, value in (await _booth_values(db, payload, exclude_id=booth.id)).items():
        setattr(booth, field, value)
    await db.flush()


async def delete_booth(db: AsyncSession, booth: Booth) -> None:
    in_use = (
        await db.execute(select(func.count()).select_from(Voter).where(Voter.booth_id == booth.id))
    ).scalar_one()
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This booth has {in_use} voters assigned to it. Move those voters to another booth first.",
        )
    await db.delete(booth)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This booth is still referenced by other records") from exc


EXPORT_COLUMNS = ["Booth No", "Polling Station", "Mandal", "Village", "Voters", "Agent Name", "Agent Mobile",
                  "Last Login", "Status", "Mapped %", "Mobile verified %", "Surveyed %"]


def export_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for b in rows:
        writer.writerow([
            b["booth_no"], b["name"] or "", b["mandal"], b["village"], b["voters"], b["agent_name"] or "",
            b["agent_mobile"] or "", b["last_login"], b["status"],
            "" if b["mapped_pct"] is None else b["mapped_pct"],
            "" if b["mobile_verified_pct"] is None else b["mobile_verified_pct"],
            "" if b["surveyed_pct"] is None else b["surveyed_pct"],
        ])
    # BOM so Excel opens the file as UTF-8 (Telugu names, etc.).
    return "﻿" + buffer.getvalue()


def booth_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Booths page cards."""
    total_voters = sum(r["voters_in_roll"] for r in rows)

    def weighted(key: str) -> int:
        if not total_voters:
            return 0
        return round(sum((r[key] or 0) * r["voters_in_roll"] for r in rows) / total_voters)

    return {
        "totalBooths": len(rows),
        "activeAgents": sum(1 for r in rows if r["last_login"] != "Never"),
        "notLoggedInAgents": sum(1 for r in rows if r["last_login"] == "Never"),
        "distinctMandals": len({r["mandal"] for r in rows}),
        "totalVoters": sum(int(r["voters"] or 0) for r in rows),
        "mappedPct": weighted("mapped_pct"),
        "mobileVerifiedPct": weighted("mobile_verified_pct"),
        "surveyedPct": weighted("surveyed_pct"),
    }
