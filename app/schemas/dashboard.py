from datetime import datetime

from pydantic import BaseModel

from app.schemas.reports import KPIWithDelta


class ActivityLogEntry(BaseModel):
    id: int
    action_type: str | None
    module: str | None
    reference_id: int | None
    description: str | None
    created_at: datetime


class DonutSlice(BaseModel):
    label: str
    count: int
    pct: float


class DashboardSummary(BaseModel):
    total_voters: KPIWithDelta
    development_works: KPIWithDelta
    govt_beneficiaries: KPIWithDelta
    cm_relief_fund: KPIWithDelta
    development_status_donut: list[DonutSlice]
    voter_gender_donut: list[DonutSlice]
    recent_activities: list[ActivityLogEntry]
