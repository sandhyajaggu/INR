from decimal import Decimal

from pydantic import BaseModel


class KPIWithDelta(BaseModel):
    value: float
    delta_pct: float | None = None


class ReportsSummary(BaseModel):
    total_beneficiaries: KPIWithDelta
    total_amount_disbursed: KPIWithDelta
    events_conducted: KPIWithDelta
    pending_requests: KPIWithDelta


class SchemePerformanceRow(BaseModel):
    scheme_name: str
    total_applications: int
    approved: int
    pending: int
    amount_disbursed: Decimal
    approval_rate_pct: float | None


class ApplicationsTrendPoint(BaseModel):
    month: str
    total_applications: int
