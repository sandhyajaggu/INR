"""Dashboard Home and Reports & Analytics (frontend: DashboardHome.jsx / mockDashboardHomeApi,
ReportsPage.jsx / mockReportsApi).

    GET /dashboard/home     getDashboardData(): kpis, voterDistribution, boothsByMandal, recentCmrf,
                            developmentWorks, voterRegistration, upcomingEvents, publicEnquiries, importantAlerts
    GET /reports            getReports(filters): summary, voters, families, booths, development, cmrf,
                            beneficiaries, enquiries, trends, surveys, communication, media, users
                            filters: mandal, village, gender (Male/Female/Other), age (18-25, 26-35, 36-50,
                            51-60, Above 60); "All ..." values mean no filter

Both respect the signed-in user's mandal / booth scope.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import and_, case, func, literal_column, or_, select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id
from app.core.scope import resolve_scope
from app.models.activity_log import ActivityLog
from app.models.cmrf import CmrfApplication
from app.models.communication import CommCampaign
from app.models.development_works import DevelopmentWork
from app.models.engagement import MediaAlbum, OutboxMessage, PublicEnquiry, VoterSurvey
from app.models.events import Event
from app.models.families import Family, FamilyMember
from app.models.geography import Booth, Mandal, Village
from app.models.multimedia import Mp3Song, PressGalleryItem, Video
from app.models.schemes import Beneficiary, Scheme
from app.models.staff import StaffUser
from app.models.voters import Voter
from app.services.user_service import user_display_role

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard Home"])
reports_router = APIRouter(prefix="/reports", tags=["Reports"])

CanViewDashboard = page_access("dashboard", "view")
CanViewReports = page_access("reports_analytics", "view")

IST = timezone(timedelta(hours=5, minutes=30))
COLORS = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#ef4444"]
CASTE_COLORS = ["#3b82f6", "#60a5fa", "#93c5fd", "#bfdbfe", "#1d4ed8", "#2563eb", "#1e40af", "#dbeafe", "#eff6ff"]
AGE_FILTERS = {"18-25": (18, 25), "26-35": (26, 35), "36-50": (36, 50), "51-60": (51, 60), "Above 60": (61, 200)}


def _pct(part: float, whole: float, digits: int = 1) -> float:
    return round(part * 100 / whole, digits) if whole else 0


def _initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _ago(value: datetime | None) -> str | None:
    if value is None:
        return None
    days = (datetime.now(timezone.utc) - value).days
    if days <= 0:
        hours = int((datetime.now(timezone.utc) - value).total_seconds() // 3600)
        return "Just now" if hours <= 0 else f"{hours} hour{'s' if hours != 1 else ''} ago"
    return f"{days} day{'s' if days != 1 else ''} ago"


def _inr(amount: float) -> str:
    if amount >= 1e7:
        return f"₹{amount / 1e7:.1f} Cr"
    if amount >= 1e5:
        return f"₹{amount / 1e5:.2f} L"
    return f"₹{amount:,.0f}"


def _today() -> date:
    return datetime.now(IST).date()


# --- dashboard home ---------------------------------------------------------------------


@dashboard_router.get("/home", summary="Dashboard Home data")
async def dashboard_home(db: DbSession, current_user: CanViewDashboard) -> dict[str, Any]:
    scope = await resolve_scope(db, current_user)
    active = Voter.removed_at.is_(None)

    mandals = list((await db.execute(select(Mandal.id, Mandal.name).order_by(Mandal.id))).all())
    if scope.restricted and scope.mandal_id:
        mandals = [m for m in mandals if m[0] == scope.mandal_id]
    colors = {mid: COLORS[i % len(COLORS)] for i, (mid, _) in enumerate(mandals)}

    voter_stmt = scope.apply(
        select(Voter.mandal_id, func.count(), func.count().filter(Voter.gender == "Male"),
               func.count().filter(Voter.gender == "Female"), func.count().filter(Voter.is_new_voter.is_(True)))
        .where(active).group_by(Voter.mandal_id),
        mandal_col=Voter.mandal_id, booth_col=Voter.booth_id,
    )
    by_mandal = {r[0]: r[1:] for r in (await db.execute(voter_stmt)).all()}
    total_voters = sum(v[0] for v in by_mandal.values())

    booth_counts = dict((await db.execute(
        scope.apply(select(Booth.mandal_id, func.count()).group_by(Booth.mandal_id), mandal_col=Booth.mandal_id, booth_col=Booth.id)
    )).all())
    max_booths = max(booth_counts.values(), default=0)

    cmrf_total = (await db.execute(scope.apply(select(func.count()).select_from(CmrfApplication), mandal_col=CmrfApplication.mandal_id))).scalar_one()
    works_total = (await db.execute(scope.apply(select(func.count()).select_from(DevelopmentWork), mandal_col=DevelopmentWork.mandal_id))).scalar_one()
    ben_total = (await db.execute(scope.apply(
        select(func.count()).select_from(Beneficiary).join(Scheme, Scheme.id == Beneficiary.scheme_id).where(Scheme.scheme_code != "cmrf"),
        mandal_col=Beneficiary.mandal_id)
    )).scalar_one()
    families_total = (await db.execute(scope.apply(select(func.count()).select_from(Family), mandal_col=Family.mandal_id))).scalar_one()
    mapped = (await db.execute(scope.apply(
        select(func.count()).select_from(FamilyMember).join(Voter, Voter.id == FamilyMember.voter_id).where(active),
        mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)
    )).scalar_one()

    today = _today()
    week = [today + timedelta(days=i) for i in range(1, 8)]
    bday_today = (await db.execute(scope.apply(
        select(func.count()).select_from(Voter).where(active, func.extract("month", Voter.dob) == today.month,
                                                      func.extract("day", Voter.dob) == today.day),
        mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)
    )).scalar_one()
    bday_week = (await db.execute(scope.apply(
        select(func.count()).select_from(Voter).where(active, or_(*[
            and_(func.extract("month", Voter.dob) == d.month, func.extract("day", Voter.dob) == d.day) for d in week
        ])),
        mandal_col=Voter.mandal_id, booth_col=Voter.booth_id)
    )).scalar_one()

    recent_cmrf = (await db.execute(scope.apply(
        select(CmrfApplication).order_by(CmrfApplication.submitted_at.desc()).limit(4), mandal_col=CmrfApplication.mandal_id)
    )).scalars().all()
    works = (await db.execute(scope.apply(
        select(DevelopmentWork).order_by(DevelopmentWork.updated_at.desc()).limit(4), mandal_col=DevelopmentWork.mandal_id)
    )).scalars().all()
    all_mandal_names = dict((await db.execute(select(Mandal.id, Mandal.name))).all())
    events = (await db.execute(scope.apply(
        select(Event).where(Event.event_date >= today, Event.status.not_in(("Cancelled", "Completed")))
        .order_by(Event.event_date, Event.event_time).limit(3), mandal_col=Event.mandal_id)
    )).scalars().all()
    enquiries = (await db.execute(select(PublicEnquiry).order_by(PublicEnquiry.received_at.desc()).limit(4))).scalars().all()

    new_enquiries = (await db.execute(select(func.count()).select_from(PublicEnquiry).where(PublicEnquiry.status == "New"))).scalar_one()
    cmrf_pending = (await db.execute(scope.apply(
        select(func.count()).select_from(CmrfApplication).where(CmrfApplication.status.in_(("Pending", "Under Review"))),
        mandal_col=CmrfApplication.mandal_id)
    )).scalar_one()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    agents = (await db.execute(scope.apply(
        select(Booth.booth_officer_mobile).where(Booth.booth_officer_mobile.is_not(None)), mandal_col=Booth.mandal_id, booth_col=Booth.id)
    )).scalars().all()
    active_agents = set((await db.execute(
        select(StaffUser.mobile).where(StaffUser.mobile.in_(agents or ["-"]), StaffUser.last_login_at >= week_ago)
    )).scalars().all())
    stale_works = (await db.execute(scope.apply(
        select(func.count()).select_from(DevelopmentWork).where(DevelopmentWork.status != "Completed",
                                                                DevelopmentWork.updated_at < datetime.now(timezone.utc) - timedelta(days=30)),
        mandal_col=DevelopmentWork.mandal_id)
    )).scalar_one()
    week_end = today + timedelta(days=7)
    distribution_events = (await db.execute(scope.apply(
        select(func.count()).select_from(Event).where(Event.event_type == "Scheme Distribution", Event.event_date >= today,
                                                      Event.event_date <= week_end, Event.status != "Cancelled"),
        mandal_col=Event.mandal_id)
    )).scalar_one()

    male = sum(v[1] for v in by_mandal.values())
    female = sum(v[2] for v in by_mandal.values())
    new_voters = sum(v[3] for v in by_mandal.values())
    return {
        "kpis": {
            "registeredVoters": total_voters,
            "pollingBooths": sum(booth_counts.values()),
            "mandalsCount": len(mandals),
            "mandalsList": ", ".join(name for _, name in mandals),
            "cmrfApplications": cmrf_total,
            "developmentWorks": works_total,
            "schemeBeneficiaries": ben_total,
            "familiesCount": families_total,
            "familiesMappedPct": f"{round(_pct(mapped, total_voters, 0))}% of voters mapped",
            "birthdaysToday": bday_today,
            "birthdaysWeek": f"{bday_week} more this week",
        },
        "voterDistribution": {
            "total": total_voters,
            "data": [
                {"mandal": name, "count": by_mandal.get(mid, (0,))[0], "pct": _pct(by_mandal.get(mid, (0,))[0], total_voters),
                 "color": colors[mid]}
                for mid, name in mandals
            ],
        },
        "boothsByMandal": [
            {"mandal": name, "booths": booth_counts.get(mid, 0),
             "heightPct": round(_pct(booth_counts.get(mid, 0), max_booths, 0)), "color": colors[mid]}
            for mid, name in mandals
        ],
        "recentCmrf": [
            {"id": f"CMRF-{a.submitted_at.astimezone(IST).year}-{a.id}", "initials": _initials(a.applicant_name),
             "name": a.applicant_name, "purpose": a.purpose, "daysAgo": _ago(a.submitted_at), "status": a.status}
            for a in recent_cmrf
        ],
        "developmentWorks": [
            {"id": format_id("DW", w.id), "title": w.title, "mandal": f"{all_mandal_names.get(w.mandal_id, '')} Mandal",
             "progress": w.progress, "img": w.completed_photo_url or w.photo_url, "status": w.status}
            for w in works
        ],
        "voterRegistration": {"total": total_voters, "newVoters": new_voters, "male": male, "female": female},
        "upcomingEvents": [
            {"id": format_id("EV", e.id), "day": e.event_date.strftime("%d"), "month": e.event_date.strftime("%b").upper(),
             "title": e.event_title, "venue": e.venue,
             "time": e.event_time.strftime("%I:%M %p") if e.event_time else None}
            for e in events
        ],
        "publicEnquiries": [
            {"id": format_id("KDK", e.id), "initials": _initials(e.citizen_name), "name": e.citizen_name,
             "category": e.enquiry_type, "timeAgo": _ago(e.received_at), "status": e.status}
            for e in enquiries
        ],
        "importantAlerts": [
            {"id": "al-1", "count": new_enquiries, "text": "New contact requests pending review", "type": "enquiry"},
            {"id": "al-2", "count": cmrf_pending, "text": "CMRF applications pending approval", "type": "cmrf"},
            {"id": "al-3", "count": len(set(agents) - active_agents), "text": "Booth agents not logged in (last 7 days)", "type": "booth"},
            {"id": "al-4", "count": stale_works, "text": "Development works due for update", "type": "dev"},
            {"id": "al-5", "count": distribution_events, "text": "Scheme distribution events this week", "type": "event"},
        ],
    }


# --- reports ------------------------------------------------------------------------------


def _clean(value: str | None, all_prefix: str) -> str | None:
    if not value or value.strip().lower().startswith(all_prefix):
        return None
    return value.strip()


@reports_router.get("", summary="Reports & Analytics (all sections)")
async def get_reports(
    db: DbSession,
    current_user: CanViewReports,
    mandal: str | None = Query(None),
    village: str | None = Query(None),
    gender: str | None = Query(None),
    age: str | None = Query(None),
) -> dict[str, Any]:
    scope = await resolve_scope(db, current_user)
    mandal, village, gender, age = _clean(mandal, "all"), _clean(village, "all"), _clean(gender, "all"), _clean(age, "all")
    mandal_id = None
    if mandal:
        mandal_id = (await db.execute(select(Mandal.id).where(func.lower(Mandal.name) == mandal.lower()))).scalar_one_or_none() or -1
    village_id = None
    if village:
        stmt = select(Village.id).where(func.lower(Village.name) == village.lower())
        if mandal_id:
            stmt = stmt.where(Village.mandal_id == mandal_id)
        village_id = (await db.execute(stmt.limit(1))).scalar_one_or_none() or -1

    def geo(stmt, mandal_col, village_col=None, booth_col=None):
        stmt = scope.apply(stmt, mandal_col=mandal_col, booth_col=booth_col)
        if mandal_id:
            stmt = stmt.where(mandal_col == mandal_id)
        if village_id and village_col is not None:
            stmt = stmt.where(village_col == village_id)
        return stmt

    voter_filter = [Voter.removed_at.is_(None)]
    if gender:
        voter_filter.append(Voter.gender == {"third gender": "Other"}.get(gender.lower(), gender.capitalize()))
    if age in AGE_FILTERS:
        lo, hi = AGE_FILTERS[age]
        voter_filter.append(Voter.age.between(lo, hi))

    def voters_q(*cols):
        return geo(select(*cols).select_from(Voter).where(*voter_filter), Voter.mandal_id, Voter.village_id, Voter.booth_id)

    # --- voters
    total, male, female, other, new, voted, verified, avg_age, villages = (await db.execute(voters_q(
        func.count(), func.count().filter(Voter.gender == "Male"), func.count().filter(Voter.gender == "Female"),
        func.count().filter(Voter.gender == "Other"), func.count().filter(Voter.is_new_voter.is_(True)),
        func.count().filter(Voter.voted_last_election.is_(True)), func.count().filter(Voter.mobile_verified.is_(True)),
        func.avg(Voter.age), func.count(func.distinct(Voter.village_id)),
    ))).one()
    band = case(
        (Voter.age.between(18, 25), "18-25"), (Voter.age.between(26, 35), "26-35"), (Voter.age.between(36, 45), "36-45"),
        (Voter.age.between(46, 60), "46-60"), (Voter.age > 60, "60+"), else_="Unknown",
    )
    bands = dict((await db.execute(voters_q(band, func.count()).group_by(literal_column("1")))).all())
    mandal_rows = (await db.execute(voters_q(Mandal.name, func.count()).join(Mandal, Mandal.id == Voter.mandal_id)
                                    .group_by(Mandal.id, Mandal.name).order_by(Mandal.id))).all()
    caste = func.coalesce(Voter.caste_category, "Not set")
    caste_rows = (await db.execute(voters_q(caste, func.count()).group_by(literal_column("1")).order_by(func.count().desc()))).all()
    mapped_voters = (await db.execute(voters_q(func.count()).where(Voter.id.in_(select(FamilyMember.voter_id))))).scalar_one()

    # --- families
    fam_stmt = geo(select(Family), Family.mandal_id, Family.village_id)
    fam_rows = [(f.members_count, f.schemes_availed, f.mandal_id, f.booth_no) for f in (await db.execute(fam_stmt)).scalars().all()]
    fam_total = len(fam_rows)
    fam_members = sum(r[0] for r in fam_rows)
    all_mandals = dict((await db.execute(select(Mandal.id, Mandal.name))).all())
    fam_by_mandal: dict[str, int] = {}
    booth_spread: dict[str, int] = {}
    for members, _, mid, booth in fam_rows:
        fam_by_mandal[all_mandals.get(mid, "—")] = fam_by_mandal.get(all_mandals.get(mid, "—"), 0) + 1
        key = f"#{booth}" if booth else "—"
        booth_spread[key] = booth_spread.get(key, 0) + 1

    # --- booths
    booth_list = (await db.execute(geo(select(Booth), Booth.mandal_id, Booth.village_id, Booth.id))).scalars().all()
    agent_mobiles = [b.booth_officer_mobile for b in booth_list if b.booth_officer_mobile]
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    active_agents = set((await db.execute(
        select(StaffUser.mobile).where(StaffUser.mobile.in_(agent_mobiles or ["-"]), StaffUser.last_login_at >= week_ago)
    )).scalars().all())

    # --- development
    dev = dict((await db.execute(geo(select(DevelopmentWork.status, func.count()), DevelopmentWork.mandal_id, DevelopmentWork.village_id)
                                 .group_by(DevelopmentWork.status))).all())
    dev_total = sum(dev.values())
    dev_cat = (await db.execute(geo(select(func.coalesce(DevelopmentWork.category, "Other"), func.count()), DevelopmentWork.mandal_id,
                                    DevelopmentWork.village_id).group_by(literal_column("1"))
                                .order_by(func.count().desc()))).all()
    dev_budget = (await db.execute(geo(select(func.coalesce(func.sum(DevelopmentWork.estimated_cost), 0)), DevelopmentWork.mandal_id,
                                       DevelopmentWork.village_id))).scalar_one()

    # --- cmrf
    cm = dict((await db.execute(geo(select(CmrfApplication.status, func.count()), CmrfApplication.mandal_id, CmrfApplication.village_id)
                                .group_by(CmrfApplication.status))).all())
    cm_amount = (await db.execute(geo(select(func.coalesce(func.sum(CmrfApplication.amount), 0)).where(CmrfApplication.status == "Approved"),
                                      CmrfApplication.mandal_id, CmrfApplication.village_id))).scalar_one()
    cm_hosp = (await db.execute(geo(select(CmrfApplication.hospital, func.count()), CmrfApplication.mandal_id, CmrfApplication.village_id)
                                .group_by(CmrfApplication.hospital).order_by(func.count().desc()).limit(10))).all()

    # --- beneficiaries
    ben = (await db.execute(geo(
        select(Scheme.scheme_name, func.count(), func.coalesce(func.sum(Beneficiary.amount).filter(Beneficiary.status == "disbursed"), 0),
               func.count().filter(Beneficiary.status == "disbursed"))
        .join(Scheme, Scheme.id == Beneficiary.scheme_id).where(Scheme.scheme_code != "cmrf").group_by(Scheme.scheme_name),
        Beneficiary.mandal_id, Beneficiary.village_id,
    ))).all()
    ben_total = sum(r[1] for r in ben)

    # --- enquiries (free-text mandal on the public form)
    enq_stmt = select(PublicEnquiry)
    if mandal:
        enq_stmt = enq_stmt.where(func.lower(PublicEnquiry.mandal) == mandal.lower())
    enquiries = (await db.execute(enq_stmt)).scalars().all()
    resolved = [e for e in enquiries if e.status == "Resolved"]
    enq_cats: dict[str, int] = {}
    for e in enquiries:
        enq_cats[e.enquiry_type] = enq_cats.get(e.enquiry_type, 0) + 1

    # --- trends (cumulative, last 6 months)
    today = _today()
    months = []
    for i in range(5, -1, -1):
        y, m = divmod(today.year * 12 + today.month - 1 - i, 12)
        start = date(y, m + 1, 1)
        ny, nm = divmod(y * 12 + m + 1, 12)
        months.append((start.strftime("%b"), datetime(ny, nm + 1, 1, tzinfo=IST)))

    async def growth(stmt, col):
        out = []
        for label, end in months:
            out.append({"month": label, "count": (await db.execute(stmt.where(col < end))).scalar_one()})
        return out

    voter_growth = await growth(voters_q(func.count()), Voter.created_at)
    works_growth = await growth(geo(select(func.count()).select_from(DevelopmentWork), DevelopmentWork.mandal_id, DevelopmentWork.village_id),
                                DevelopmentWork.created_at)
    enq_growth = await growth(select(func.count()).select_from(PublicEnquiry), PublicEnquiry.received_at)

    # --- surveys
    srv_stmt = geo(select(VoterSurvey).join(Voter, Voter.id == VoterSurvey.voter_id), Voter.mandal_id, Voter.village_id, Voter.booth_id)
    surveys = (await db.execute(srv_stmt)).scalars().all()
    s_total = len(surveys)
    welfare = [a for s in surveys for a in (s.answers or []) if "welfare" in str(a.get("question", "")).lower()
               or "scheme" in str(a.get("question", "")).lower()]
    welfare_yes = [a for a in welfare if str(a.get("answer", "")).lower().startswith(("yes", "on time"))]
    surveyed_booths = (await db.execute(
        select(func.count(func.distinct(Voter.booth_id))).select_from(VoterSurvey).join(Voter, Voter.id == VoterSurvey.voter_id)
        .where(Voter.booth_id.in_([b.id for b in booth_list] or [-1]))
    )).scalar_one()

    # --- communication
    out_stats = dict((await db.execute(
        select(func.concat(OutboxMessage.channel, ":", OutboxMessage.status), func.count())
        .where(OutboxMessage.source == "campaign").group_by(OutboxMessage.channel, OutboxMessage.status)
    )).all())

    def ch(channel: str, *statuses: str) -> int:
        return sum(out_stats.get(f"{channel}:{s}", 0) for s in statuses)

    def ch_total(channel: str) -> int:
        return sum(v for k, v in out_stats.items() if k.startswith(f"{channel}:") and not k.endswith("Cancelled"))

    wa_sent = ch("whatsapp", "Sent", "Delivered", "Read")
    sms_sent = ch("sms", "Sent", "Delivered", "Read")
    calls_total = ch_total("voice")

    # --- media
    photos = sum(len(a.photos or []) for a in (await db.execute(select(MediaAlbum))).scalars().all())
    videos = (await db.execute(select(func.count()).select_from(Video))).scalar_one()
    press = (await db.execute(select(func.count()).select_from(PressGalleryItem))).scalar_one()
    mp3 = (await db.execute(select(func.count()).select_from(Mp3Song))).scalar_one()
    ev_count, attendees = (await db.execute(geo(select(func.count(), func.coalesce(func.sum(Event.expected_attendance), 0)),
                                                Event.mandal_id, Event.village_id))).one()

    # --- users
    users = (await db.execute(select(StaffUser))).scalars().all()
    roles: dict[str, int] = {}
    for u in users:
        roles[user_display_role(u)] = roles.get(user_display_role(u), 0) + 1
    log_counts = dict((await db.execute(
        select(case(
            (ActivityLog.action_type == "signed_in", "Logins"),
            (ActivityLog.action_type.like("voter_%"), "Voter Edits"),
            (ActivityLog.action_type == "voter_survey_added", "Surveys Logged"),
            (ActivityLog.description.ilike("%export%"), "Exports"),
            else_="Other",
        ), func.count()).group_by(literal_column("1"))
    )).all())
    log_total = sum(log_counts.values())

    caste_total = sum(n for _, n in caste_rows)
    return {
        "summary": {
            "total_voters": total,
            "booths": len(booth_list),
            "dev_budget": _inr(float(dev_budget)),
            "cmrf_amount": _inr(float(cm_amount)),
            "schemes": (await db.execute(select(func.count()).select_from(Scheme).where(Scheme.scheme_code != "cmrf", Scheme.status == "active"))).scalar_one(),
            "events": ev_count,
        },
        "voters": {
            "gender": {"male": _pct(male, total), "female": _pct(female, total), "third_gender": _pct(other, total),
                       "male_count": male, "female_count": female, "third_gender_count": other, "total": total},
            "age_groups": [{"band": b, "count": bands.get(b, 0), "pct": _pct(bands.get(b, 0), total)}
                           for b in ("18-25", "26-35", "36-45", "46-60", "60+")],
            "voting_metrics": {"voted_last_election": f"{round(_pct(voted, total))}%", "new_voters": new,
                               "avg_age": round(float(avg_age), 1) if avg_age else None, "villages_covered": villages},
            "by_mandal": [{"mandal": n, "count": c, "color": COLORS[i % len(COLORS)]} for i, (n, c) in enumerate(mandal_rows)],
            "by_caste": [{"name": n, "count": c, "pct": _pct(c, caste_total), "color": CASTE_COLORS[i % len(CASTE_COLORS)]}
                         for i, (n, c) in enumerate(caste_rows)],
            "verification": {"mobile_verified": verified, "pending": total - verified},
            "family_mapped": {"mapped": mapped_voters, "unmapped": total - mapped_voters},
        },
        "families": {
            "total_families": fam_total,
            "members": fam_members,
            "avg_size": round(fam_members / fam_total, 1) if fam_total else 0,
            "with_scheme_pct": f"{round(_pct(sum(1 for r in fam_rows if r[1] > 0), fam_total))}%",
            "schemes_per_family": [
                {"count": k if k < 4 else "4+", "families": n, "pct": round(_pct(n, fam_total))}
                for k, n in ((k, sum(1 for r in fam_rows if (r[1] if r[1] < 4 else 4) == k)) for k in range(5))
            ],
            "by_mandal": [{"mandal": n, "count": c, "color": COLORS[i % len(COLORS)]} for i, (n, c) in enumerate(fam_by_mandal.items())],
            "booth_spread": [{"booth": b, "count": c} for b, c in sorted(booth_spread.items(), key=lambda kv: -kv[1])[:20]],
            "member_distribution": [
                {"size": label, "count": n, "pct": round(_pct(n, fam_total))}
                for label, n in (
                    ("1 Member", sum(1 for r in fam_rows if r[0] <= 1)),
                    ("2-3 Members", sum(1 for r in fam_rows if 2 <= r[0] <= 3)),
                    ("4+ Members", sum(1 for r in fam_rows if r[0] >= 4)),
                )
            ],
        },
        "booths": {
            "agents_active": len(set(agent_mobiles) & active_agents),
            "agents_inactive": len(set(agent_mobiles) - active_agents),
            "avg_voters_per_booth": round(sum(b.total_voters or 0 for b in booth_list) / len(booth_list)) if booth_list else 0,
            "turnout_estimate": f"{round(_pct(voted, total))}%",
        },
        "development": {
            "total_works": dev_total, "completed": dev.get("Completed", 0), "in_progress": dev.get("In Progress", 0),
            "not_started": dev.get("Not Started", 0),
            "by_category": [{"name": n, "count": c, "pct": round(_pct(c, dev_total))} for n, c in dev_cat],
        },
        "cmrf": {
            "total_applications": sum(cm.values()), "approved": cm.get("Approved", 0), "under_review": cm.get("Under Review", 0),
            "rejected": cm.get("Rejected", 0), "pending": cm.get("Pending", 0), "disbursed_amount": float(cm_amount),
            "by_hospital": [{"name": n, "count": c} for n, c in cm_hosp],
        },
        "beneficiaries": {
            "total_beneficiaries": ben_total,
            "total_disbursed": float(sum(r[2] for r in ben)),
            "disbursed_pct": round(_pct(sum(r[3] for r in ben), ben_total)),
            "schemes": [{"name": n, "count": c, "amount": float(a), "pct": round(_pct(c, ben_total))} for n, c, a, _ in ben],
        },
        "enquiries": {
            "total": len(enquiries),
            "resolved": len(resolved),
            "under_review": sum(1 for e in enquiries if e.status == "In Progress"),
            "pending": sum(1 for e in enquiries if e.status == "New"),
            "avg_resolution_days": (f"{sum((e.updated_at - e.received_at).total_seconds() for e in resolved) / 86400 / len(resolved):.1f}"
                                    if resolved else None),
            "by_category": [{"name": n, "count": c, "pct": round(_pct(c, len(enquiries)))}
                            for n, c in sorted(enq_cats.items(), key=lambda kv: -kv[1])],
        },
        "trends": {"voter_growth": voter_growth, "works_growth": works_growth, "enquiries_growth": enq_growth},
        "surveys": {
            "total_responses": s_total,
            "positive_pct": round(_pct(sum(1 for s in surveys if (s.feedback or "").lower() == "positive"), s_total)),
            "negative_pct": round(_pct(sum(1 for s in surveys if (s.feedback or "").lower() == "negative"), s_total)),
            "tdp_support": round(_pct(sum(1 for s in surveys if (s.party_support or "").upper().startswith("TDP")), s_total)),
            "welfare_satisfaction": round(_pct(len(welfare_yes), len(welfare))) if welfare else None,
            "booth_coverage": round(_pct(surveyed_booths, len(booth_list))),
        },
        "communication": {
            "total_outreach": sum(v for k, v in out_stats.items() if not k.endswith("Cancelled")),
            "whatsapp": {"sent": wa_sent, "queued": ch("whatsapp", "Queued", "Scheduled"),
                         "delivered": round(_pct(ch("whatsapp", "Delivered", "Read"), wa_sent)),
                         "read": round(_pct(ch("whatsapp", "Read"), wa_sent))},
            "sms": {"sent": sms_sent, "queued": ch("sms", "Queued", "Scheduled"),
                    "delivered": round(_pct(ch("sms", "Delivered", "Read"), sms_sent)),
                    "failed": round(_pct(ch("sms", "Failed"), sms_sent + ch("sms", "Failed")))},
            "ai_calls": {"total": calls_total, "connected": round(_pct(ch("voice", "Delivered", "Read"), calls_total))},
            "campaigns": (await db.execute(select(func.count()).select_from(CommCampaign))).scalar_one(),
        },
        "media": {
            "total_items": photos + videos + press + mp3,
            "photos": photos,
            "videos": videos,
            "press_releases": press,
            "events_count": ev_count,
            "attendees": f"{int(attendees):,}",
        },
        "users": {
            "total_users": len(users),
            "roles": [{"name": n, "count": c, "pct": round(_pct(c, len(users)))} for n, c in sorted(roles.items(), key=lambda kv: -kv[1])],
            "audit_logs_count": log_total,
            "recent_actions": [{"type": t, "count": log_counts.get(t, 0), "pct": round(_pct(log_counts.get(t, 0), log_total))}
                               for t in ("Logins", "Voter Edits", "Surveys Logged", "Exports")],
        },
        "filters": {"mandal": mandal, "village": village, "gender": gender, "age": age},
    }
