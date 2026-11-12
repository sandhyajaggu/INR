"""Dashboard notifications — the bell in AdminNav and the sidebar badges.

    GET    /notifications                  current user's notifications (newest first, paginated)
    GET    /notifications/unread-count     {"count": n, "by_page": {page_key: n}}
    GET    /notifications/{id}             one notification
    PATCH  /notifications/{id}/read        mark one read     (body optional: {"is_read": false} marks unread)
    POST   /notifications/read-all         mark all read     (optional ?page_key=public_enquiry)
    DELETE /notifications/{id}             delete one
    DELETE /notifications                  clear all read notifications
    POST   /notifications                  admin announcement to staff (super_admin / admin)

Every user only ever sees and changes their own notifications.
Created automatically for: new public enquiries, new war-room alerts.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from app.core.access import PAGE_KEYS
from app.core.dependencies import CurrentUser, DbSession, RequireStaff
from app.core.ids import parse_id
from app.models.notifications import Notification
from app.services.notification_service import notification_row, notify_page

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class ReadUpdate(BaseModel):
    is_read: bool = True


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=2000)
    link: str | None = Field(default=None, max_length=300)
    page_key: str | None = Field(default=None, description="Only staff who can view this page receive it; omit for everyone")


async def _own(db, notification_id: str, user_id: int) -> Notification:
    obj = await db.get(Notification, parse_id(notification_id, label="Notification"))
    if obj is None or obj.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return obj


@router.get("", summary="List my notifications (newest first)")
async def list_notifications(
    db: DbSession,
    current_user: CurrentUser,
    unread: bool | None = Query(None, description="true = only unread, false = only read"),
    page_key: str | None = Query(None, description="Filter by page, e.g. public_enquiry"),
    type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    conds = [Notification.user_id == current_user.id]
    if unread is not None:
        conds.append(Notification.is_read.is_(not unread))
    if page_key:
        conds.append(Notification.page_key == page_key)
    if type:
        conds.append(Notification.type == type)
    total = (await db.execute(select(func.count()).select_from(Notification).where(*conds))).scalar_one()
    unread_count = (
        await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == current_user.id, Notification.is_read.is_(False)
            )
        )
    ).scalar_one()
    rows = (
        await db.execute(
            select(Notification).where(*conds)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [notification_row(n) for n in rows],
        "total": total,
        "unread": unread_count,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/unread-count", summary="Unread count for the bell and per-page sidebar badges")
async def unread_count(db: DbSession, current_user: CurrentUser) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(Notification.page_key, func.count())
            .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
            .group_by(Notification.page_key)
        )
    ).all()
    by_page = {key: n for key, n in rows if key}
    return {"count": sum(n for _, n in rows), "by_page": by_page}


@router.post("/read-all", summary="Mark all my notifications read")
async def mark_all_read(
    db: DbSession, current_user: CurrentUser, page_key: str | None = Query(None)
) -> dict[str, Any]:
    stmt = update(Notification).where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
    if page_key:
        stmt = stmt.where(Notification.page_key == page_key)
    result = await db.execute(stmt.values(is_read=True, read_at=datetime.now(timezone.utc)))
    await db.commit()
    return {"success": True, "updated": result.rowcount}


@router.delete("", summary="Clear all my read notifications")
async def clear_read(db: DbSession, current_user: CurrentUser) -> dict[str, Any]:
    result = await db.execute(
        delete(Notification).where(Notification.user_id == current_user.id, Notification.is_read.is_(True))
    )
    await db.commit()
    return {"success": True, "deleted": result.rowcount}


@router.post("", status_code=status.HTTP_201_CREATED, summary="Send an announcement to staff (admin)")
async def create_announcement(payload: AnnouncementCreate, db: DbSession, current_user: RequireStaff) -> dict[str, Any]:
    if payload.page_key and payload.page_key not in PAGE_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown page '{payload.page_key}'")
    sent = await notify_page(
        db,
        payload.page_key,
        type="announcement",
        title=payload.title.strip(),
        message=payload.message,
        link=payload.link or None,
        created_by=current_user.id,
        exclude_user_id=current_user.id,
    )
    await db.commit()
    return {"success": True, "recipients": sent}


@router.get("/{notification_id}", summary="One notification")
async def get_notification(notification_id: str, db: DbSession, current_user: CurrentUser) -> dict[str, Any]:
    return notification_row(await _own(db, notification_id, current_user.id))


@router.patch("/{notification_id}/read", summary="Mark one notification read (or unread)")
async def mark_read(
    notification_id: str, db: DbSession, current_user: CurrentUser, payload: ReadUpdate | None = None
) -> dict[str, Any]:
    obj = await _own(db, notification_id, current_user.id)
    is_read = payload.is_read if payload else True
    obj.is_read = is_read
    obj.read_at = datetime.now(timezone.utc) if is_read else None
    await db.commit()
    await db.refresh(obj)
    return notification_row(obj)


@router.delete("/{notification_id}", summary="Delete one notification")
async def delete_notification(notification_id: str, db: DbSession, current_user: CurrentUser) -> dict[str, bool]:
    obj = await _own(db, notification_id, current_user.id)
    await db.delete(obj)
    await db.commit()
    return {"success": True}
