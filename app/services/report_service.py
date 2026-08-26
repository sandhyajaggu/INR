"""Shared month-over-month KPI helpers for the Dashboard Home and Reports modules."""

from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.reports import KPIWithDelta


def _month_start(months_ago: int) -> date:
    today = date.today()
    total_months = today.year * 12 + (today.month - 1) - months_ago
    year, month0 = divmod(total_months, 12)
    return date(year, month0 + 1, 1)


def _next_month_start(d: date) -> date:
    total_months = d.year * 12 + (d.month - 1) + 1
    year, month0 = divmod(total_months, 12)
    return date(year, month0 + 1, 1)


def _pct_change(previous: float, current: float) -> float | None:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 2)


async def count_with_mom(
    db: AsyncSession, model, date_column: ColumnElement, extra_conditions: Sequence[ColumnElement] = ()
) -> KPIWithDelta:
    base = select(func.count()).select_from(model)
    for condition in extra_conditions:
        base = base.where(condition)

    total = (await db.execute(base)).scalar_one()

    this_start = _month_start(0)
    prev_start = _month_start(1)

    this_month = (
        await db.execute(base.where(date_column >= this_start, date_column < _next_month_start(this_start)))
    ).scalar_one()
    prev_month = (await db.execute(base.where(date_column >= prev_start, date_column < this_start))).scalar_one()

    return KPIWithDelta(value=total, delta_pct=_pct_change(prev_month, this_month))


async def sum_with_mom(
    db: AsyncSession,
    model,
    amount_column: ColumnElement,
    date_column: ColumnElement,
    extra_conditions: Sequence[ColumnElement] = (),
) -> KPIWithDelta:
    base = select(func.coalesce(func.sum(amount_column), 0)).select_from(model)
    for condition in extra_conditions:
        base = base.where(condition)

    total = (await db.execute(base)).scalar_one()

    this_start = _month_start(0)
    prev_start = _month_start(1)

    this_month = (
        await db.execute(base.where(date_column >= this_start, date_column < _next_month_start(this_start)))
    ).scalar_one()
    prev_month = (await db.execute(base.where(date_column >= prev_start, date_column < this_start))).scalar_one()

    return KPIWithDelta(value=float(total or 0), delta_pct=_pct_change(float(prev_month or 0), float(this_month or 0)))
