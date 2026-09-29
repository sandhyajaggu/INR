"""Booth Summary page (Super Admin → Booths → All Booths).

Every booth is returned with its mandal/village *names* (not IDs), plus the
turnout figures the table shows, calculated from Registered Votes
(total_voters) and votes_polled.

Summary-card status buckets:
    Completed = status "On Time"
    Delayed   = status "Delayed"
    Pending   = no status yet (booth added but not updated)
"""

import csv
import io
from math import ceil

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geography import Booth, Mandal, Village
from app.schemas.common import PaginatedResponse
from app.schemas.geography import BoothCreate, BoothOut, BoothSummary
from app.services.geography_service import resolve_geography

STATUS_COMPLETED = "On Time"
STATUS_DELAYED = "Delayed"
STATUS_PENDING = "Pending"  # filter value only; stored as NULL

EXPORT_COLUMNS = [
    "Booth No", "In-Charge Name", "Mandal", "Village", "Votes Polled", "Registered Votes",
    "Pending Votes", "Voting %", "TDP", "YSP", "Janasena", "Congress", "Turnout", "Status",
]


def _percentage(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def to_booth_out(booth: Booth, mandal_name: str, village_name: str) -> BoothOut:
    registered = booth.total_voters or 0
    polled = booth.votes_polled or 0
    turnout = _percentage(polled, registered)
    return BoothOut(
        id=booth.id,
        booth_number=booth.booth_number,
        booth_name=booth.booth_name,
        mandal_name=mandal_name,
        village_name=village_name,
        location_address=booth.location_address,
        booth_officer_name=booth.booth_officer_name,
        booth_officer_mobile=booth.booth_officer_mobile,
        votes_polled=polled,
        total_voters=registered,
        pending_votes=max(registered - polled, 0),
        voting_percentage=turnout,
        tdp_votes=booth.tdp_votes,
        ysp_votes=booth.ysp_votes,
        janasena_votes=booth.janasena_votes,
        congress_votes=booth.congress_votes,
        turnout=turnout,
        status=booth.status,
        created_at=booth.created_at,
    )


def _apply_filters(
    stmt: Select,
    *,
    mandal_name: str | None,
    village_name: str | None,
    q: str | None,
    status_filter: str | None,
) -> Select:
    if mandal_name and mandal_name.strip():
        stmt = stmt.where(func.lower(Mandal.name) == mandal_name.strip().lower())
    if village_name and village_name.strip():
        stmt = stmt.where(func.lower(Village.name) == village_name.strip().lower())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Booth.booth_number.ilike(pattern), Booth.booth_officer_name.ilike(pattern)))
    if status_filter:
        if status_filter == STATUS_PENDING:
            stmt = stmt.where(Booth.status.is_(None))
        else:
            stmt = stmt.where(Booth.status == status_filter)
    return stmt


def _booth_rows_query() -> Select:
    return (
        select(Booth, Mandal.name, Village.name)
        .join(Mandal, Booth.mandal_id == Mandal.id)
        .join(Village, Booth.village_id == Village.id)
    )


def _ordered(stmt: Select) -> Select:
    # Booth numbers are text ("001", "12", "293"); ordering by length first
    # keeps them in numeric order without breaking on non-numeric numbers.
    return stmt.order_by(Mandal.name, func.length(Booth.booth_number), Booth.booth_number)


async def list_booths(
    db: AsyncSession,
    *,
    mandal_name: str | None,
    village_name: str | None,
    q: str | None,
    status_filter: str | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[BoothOut]:
    filters = dict(mandal_name=mandal_name, village_name=village_name, q=q, status_filter=status_filter)
    count_stmt = _apply_filters(
        select(func.count(Booth.id))
        .join(Mandal, Booth.mandal_id == Mandal.id)
        .join(Village, Booth.village_id == Village.id),
        **filters,
    )
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = _ordered(_apply_filters(_booth_rows_query(), **filters)).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).all()
    return PaginatedResponse(
        items=[to_booth_out(b, m, v) for b, m, v in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if page_size else 0,
    )


async def booth_summary(
    db: AsyncSession, *, mandal_name: str | None, village_name: str | None, q: str | None
) -> BoothSummary:
    stmt = _apply_filters(
        select(
            func.count(Booth.id),
            func.count(Booth.id).filter(Booth.status == STATUS_COMPLETED),
            func.count(Booth.id).filter(Booth.status == STATUS_DELAYED),
            func.count(Booth.id).filter(Booth.status.is_(None)),
        )
        .join(Mandal, Booth.mandal_id == Mandal.id)
        .join(Village, Booth.village_id == Village.id),
        mandal_name=mandal_name,
        village_name=village_name,
        q=q,
        status_filter=None,
    )
    total, completed, delayed, pending = (await db.execute(stmt)).one()
    return BoothSummary(
        total_booths=total,
        completed=completed,
        completed_percentage=_percentage(completed, total),
        pending=pending,
        pending_percentage=_percentage(pending, total),
        delayed=delayed,
        delayed_percentage=_percentage(delayed, total),
    )


async def export_booths_csv(
    db: AsyncSession,
    *,
    mandal_name: str | None,
    village_name: str | None,
    q: str | None,
    status_filter: str | None,
) -> str:
    stmt = _ordered(
        _apply_filters(
            _booth_rows_query(), mandal_name=mandal_name, village_name=village_name, q=q, status_filter=status_filter
        )
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for booth, mandal, village in (await db.execute(stmt)).all():
        row = to_booth_out(booth, mandal, village)
        writer.writerow([
            row.booth_number, row.booth_officer_name or "", row.mandal_name, row.village_name,
            row.votes_polled, row.total_voters, row.pending_votes, f"{row.voting_percentage}%",
            row.tdp_votes, row.ysp_votes, row.janasena_votes, row.congress_votes,
            f"{row.turnout}%", row.status or STATUS_PENDING,
        ])
    # BOM so Excel opens the file as UTF-8 (Telugu names, etc.).
    return "﻿" + buffer.getvalue()


async def get_booth_out(db: AsyncSession, booth_id: int) -> BoothOut:
    row = (await db.execute(_booth_rows_query().where(Booth.id == booth_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booth not found")
    return to_booth_out(*row)


async def _booth_values(db: AsyncSession, payload: BoothCreate, exclude_id: int | None) -> dict:
    data = payload.model_dump()
    mandal_id, village_id = await resolve_geography(
        db, mandal_name=data.pop("mandal_name"), village_name=data.pop("village_name")
    )
    duplicate = select(Booth.id).where(Booth.mandal_id == mandal_id, Booth.booth_number == data["booth_number"])
    if exclude_id is not None:
        duplicate = duplicate.where(Booth.id != exclude_id)
    if (await db.execute(duplicate)).first() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Booth No '{data['booth_number']}' already exists in this mandal"
        )
    return {**data, "mandal_id": mandal_id, "village_id": village_id}


async def create_booth(db: AsyncSession, payload: BoothCreate) -> BoothOut:
    booth = Booth(**await _booth_values(db, payload, exclude_id=None))
    db.add(booth)
    await db.commit()
    return await get_booth_out(db, booth.id)


async def update_booth(db: AsyncSession, booth_id: int, payload: BoothCreate) -> BoothOut:
    booth = await db.get(Booth, booth_id)
    if booth is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booth not found")
    for field, value in (await _booth_values(db, payload, exclude_id=booth_id)).items():
        setattr(booth, field, value)
    await db.commit()
    return await get_booth_out(db, booth_id)


async def delete_booth(db: AsyncSession, booth_id: int) -> None:
    booth = await db.get(Booth, booth_id)
    if booth is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booth not found")
    await db.delete(booth)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This booth has voters assigned to it. Move those voters to another booth first."
        ) from None
