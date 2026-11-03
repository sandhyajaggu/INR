"""Audit Logs (frontend: AdminAuditLogs.jsx / AuditDrawer.jsx, mockAuditApi).

    GET  /audit-logs   -> getAuditLogs()  [{id, user, action, module, at, changes, img, ip}]
    POST /audit-logs   -> logEvent({action, module, changes, img})

`changes` is a list of [field, before, after]. Newest first.
"""

from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.core.dependencies import CurrentUser, DbSession, page_access
from app.core.ids import format_id
from app.models.activity_log import ActivityLog
from app.services.activity_service import client_ip, log_activity

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

CanView = page_access("audit_logs", "view")


class AuditLogOut(BaseModel):
    id: str
    user: str | None
    action: str | None
    module: str | None
    at: datetime
    changes: list[list[Any]]
    img: str | None
    ip: str | None


class AuditLogCreate(BaseModel):
    action: str = Field(min_length=1)
    module: str = Field(min_length=1)
    changes: list[list[Any]] = []
    img: str | None = None


def module_label(module: str | None) -> str | None:
    """'development_works' -> 'Development Works'; labels already in title case pass through."""
    if not module:
        return module
    if module != module.lower():
        return module
    return module.replace("_", " ").title()


def serialize_log(row: ActivityLog) -> dict[str, Any]:
    return {
        "id": format_id("AL", row.id),
        "user": row.actor_name,
        "action": row.description,
        "module": module_label(row.module),
        "at": row.created_at,
        "changes": row.changes or [],
        "img": row.screenshot_url,
        "ip": row.ip_address,
    }


@router.get("", response_model=list[AuditLogOut], summary="List audit log entries (newest first)")
async def get_audit_logs(
    db: DbSession,
    current_user: CanView,
    user: str | None = Query(None, description="Filter by user name (contains)"),
    module: str | None = Query(None),
    q: str | None = Query(None, description="Search in action text"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
) -> list[dict[str, Any]]:
    stmt = select(ActivityLog)
    if user:
        stmt = stmt.where(ActivityLog.actor_name.ilike(f"%{user}%"))
    if module:
        stmt = stmt.where(
            or_(
                func.lower(ActivityLog.module) == module.lower(),
                func.lower(ActivityLog.module) == module.lower().replace(" ", "_"),
            )
        )
    if q:
        stmt = stmt.where(ActivityLog.description.ilike(f"%{q}%"))
    if date_from:
        stmt = stmt.where(ActivityLog.created_at >= datetime.combine(date_from, time.min, timezone.utc))
    if date_to:
        stmt = stmt.where(ActivityLog.created_at <= datetime.combine(date_to, time.max, timezone.utc))
    rows = (await db.execute(stmt.order_by(ActivityLog.id.desc()).limit(limit))).scalars().all()
    return [serialize_log(r) for r in rows]


@router.post(
    "",
    response_model=AuditLogOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record an event from the frontend (logEvent)",
)
async def log_event(payload: AuditLogCreate, request: Request, db: DbSession, current_user: CurrentUser) -> dict:
    await log_activity(
        db,
        actor_id=current_user.id,
        actor_name=current_user.name,
        action_type="client_event",
        module=payload.module,
        reference_id=None,
        description=payload.action,
        changes=payload.changes,
        screenshot_url=payload.img,
        ip_address=client_ip(request),
    )
    await db.commit()
    row = (
        await db.execute(
            select(ActivityLog).where(ActivityLog.actor_id == current_user.id).order_by(ActivityLog.id.desc()).limit(1)
        )
    ).scalar_one()
    return serialize_log(row)
