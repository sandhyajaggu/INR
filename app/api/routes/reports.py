from fastapi import APIRouter
from sqlalchemy import text

from app.core.dependencies import CurrentUser, DbSession
from app.models.events import Event
from app.models.schemes import Beneficiary
from app.schemas.reports import ApplicationsTrendPoint, ReportsSummary, SchemePerformanceRow
from app.services.report_service import count_with_mom, sum_with_mom

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/summary", response_model=ReportsSummary, summary="Reports module summary cards")
async def reports_summary(db: DbSession, current_user: CurrentUser) -> ReportsSummary:
    total_beneficiaries = await count_with_mom(db, Beneficiary, Beneficiary.application_date)
    total_amount_disbursed = await sum_with_mom(
        db,
        Beneficiary,
        Beneficiary.amount,
        Beneficiary.application_date,
        extra_conditions=[Beneficiary.status == "disbursed"],
    )
    events_conducted = await count_with_mom(
        db, Event, Event.event_date, extra_conditions=[Event.status == "completed"]
    )
    pending_requests = await count_with_mom(
        db, Beneficiary, Beneficiary.application_date, extra_conditions=[Beneficiary.status == "pending"]
    )

    return ReportsSummary(
        total_beneficiaries=total_beneficiaries,
        total_amount_disbursed=total_amount_disbursed,
        events_conducted=events_conducted,
        pending_requests=pending_requests,
    )


@router.get(
    "/scheme-performance",
    response_model=list[SchemePerformanceRow],
    summary="Scheme-wise performance table (v_scheme_performance)",
)
async def scheme_performance(db: DbSession, current_user: CurrentUser) -> list[SchemePerformanceRow]:
    result = await db.execute(
        text(
            "SELECT scheme_name, total_applications, approved, pending, amount_disbursed, approval_rate_pct "
            "FROM v_scheme_performance ORDER BY scheme_name"
        )
    )
    return [SchemePerformanceRow(**row._mapping) for row in result]


@router.get(
    "/applications-trend",
    response_model=list[ApplicationsTrendPoint],
    summary="Applications over time, grouped by month",
)
async def applications_trend(db: DbSession, current_user: CurrentUser) -> list[ApplicationsTrendPoint]:
    result = await db.execute(
        text(
            "SELECT to_char(date_trunc('month', application_date), 'YYYY-MM') AS month, COUNT(*) AS total_applications "
            "FROM beneficiaries WHERE application_date IS NOT NULL "
            "GROUP BY 1 ORDER BY 1"
        )
    )
    return [ApplicationsTrendPoint(month=row.month, total_applications=row.total_applications) for row in result]
