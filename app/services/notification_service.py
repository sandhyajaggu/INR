"""Create dashboard notifications.

`notify_page` fans one event out to every active staff user who can view the
given page (super_admin always can). It only adds rows to the session; the
caller's own commit saves them together with the record that caused them.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import has_access
from app.core.ids import format_id
from app.models.notifications import Notification
from app.models.staff import StaffUser

# Frontend routes (DashboardRoutes.js) a notification opens.
PAGE_LINKS: dict[str, str] = {
    "public_enquiry": "/dashboard/PublicEnquiryRequests",
    "surveys_campaigns": "/dashboard/Surveys",
    "cmrf_applications": "/dashboard/CMRF",
    "events": "/dashboard/EventsTable",
    "dashboard": "/dashboard/dashboard-home",
}


async def recipients_for_page(db: AsyncSession, page_key: str | None) -> list[StaffUser]:
    users = (await db.execute(select(StaffUser).where(StaffUser.status == "active"))).scalars().all()
    if page_key is None:
        return list(users)
    return [u for u in users if has_access(u, page_key, "view")]


async def notify_page(
    db: AsyncSession,
    page_key: str | None,
    *,
    type: str,
    title: str,
    message: str | None = None,
    link: str | None = None,
    reference_id: str | None = None,
    exclude_user_id: int | None = None,
    created_by: int | None = None,
) -> int:
    """Add one notification per recipient. Returns how many were added."""
    users = await recipients_for_page(db, page_key)
    count = 0
    for user in users:
        if user.id == exclude_user_id:
            continue
        db.add(
            Notification(
                user_id=user.id,
                type=type,
                title=title[:200],
                message=message,
                link=link if link is not None else PAGE_LINKS.get(page_key or ""),
                page_key=page_key,
                reference_id=reference_id,
                created_by=created_by,
            )
        )
        count += 1
    return count


def notification_row(n: Notification) -> dict[str, Any]:
    return {
        "id": format_id("NTF", n.id),
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "link": n.link,
        "page": n.page_key,
        "reference_id": n.reference_id,
        "is_read": n.is_read,
        "read_at": n.read_at,
        "created_at": n.created_at,
    }
