from fastapi import APIRouter
from sqlalchemy import select, text

from app.core.dependencies import CurrentUser, DbSession
from app.models.development_works import DevelopmentWork
from app.models.schemes import Beneficiary, Scheme
from app.models.voters import Voter
from app.schemas.dashboard import ActivityLogEntry, DashboardSummary, DonutSlice
from app.services.report_service import count_with_mom

router = APIRouter(prefix="/dashboard", tags=["Dashboard Home"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard Home — all KPI cards, both donut charts, and recent activity in one call",
)
async def dashboard_summary(db: DbSession, current_user: CurrentUser) -> DashboardSummary:
    total_voters = await count_with_mom(db, Voter, Voter.created_at)
    development_works = await count_with_mom(db, DevelopmentWork, DevelopmentWork.created_at)
    govt_beneficiaries = await count_with_mom(db, Beneficiary, Beneficiary.created_at)

    cmrf_scheme_id = (
        await db.execute(select(Scheme.id).where(Scheme.scheme_code == "cmrf"))
    ).scalar_one_or_none()
    cmrf_condition = [Beneficiary.scheme_id == cmrf_scheme_id] if cmrf_scheme_id is not None else [Beneficiary.id == -1]
    cm_relief_fund = await count_with_mom(db, Beneficiary, Beneficiary.created_at, extra_conditions=cmrf_condition)

    dev_status_rows = (
        await db.execute(text("SELECT status, total FROM v_development_status_summary"))
    ).all()
    dev_total = sum(row.total for row in dev_status_rows) or 1
    development_status_donut = [
        DonutSlice(label=row.status, count=row.total, pct=round(row.total / dev_total * 100, 2))
        for row in dev_status_rows
    ]

    gender_rows = (await db.execute(text("SELECT gender, total FROM v_voter_gender_distribution"))).all()
    gender_total = sum(row.total for row in gender_rows) or 1
    voter_gender_donut = [
        DonutSlice(label=row.gender or "Unspecified", count=row.total, pct=round(row.total / gender_total * 100, 2))
        for row in gender_rows
    ]

    activity_rows = (
        await db.execute(
            text(
                "SELECT id, action_type, module, reference_id, description, created_at "
                "FROM activity_log ORDER BY created_at DESC LIMIT 10"
            )
        )
    ).all()
    recent_activities = [ActivityLogEntry(**row._mapping) for row in activity_rows]

    return DashboardSummary(
        total_voters=total_voters,
        development_works=development_works,
        govt_beneficiaries=govt_beneficiaries,
        cm_relief_fund=cm_relief_fund,
        development_status_donut=development_status_donut,
        voter_gender_donut=voter_gender_donut,
        recent_activities=recent_activities,
    )
