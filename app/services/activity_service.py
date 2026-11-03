from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.staff import StaffUser


async def log_activity(
    db: AsyncSession,
    *,
    actor_id: int | None,
    action_type: str,
    module: str,
    reference_id: int | None,
    description: str,
    changes: list[list[Any]] | None = None,
    screenshot_url: str | None = None,
    ip_address: str | None = None,
    actor_name: str | None = None,
    commit: bool = False,
) -> None:
    """Reusable activity-log writer (feeds the Audit Logs page).

    `changes` is a list of [field, before, after] triples. Not committed by
    default — call sites that already manage a transaction can flush it
    alongside their own commit; pass commit=True for a standalone call.
    """
    if actor_name is None and actor_id is not None:
        actor = await db.get(StaffUser, actor_id)
        actor_name = actor.name if actor else None
    entry = ActivityLog(
        actor_id=actor_id,
        actor_name=actor_name,
        action_type=action_type,
        module=module,
        reference_id=reference_id,
        description=description,
        changes=changes or [],
        screenshot_url=screenshot_url,
        ip_address=ip_address,
    )
    db.add(entry)
    if commit:
        await db.commit()
    else:
        await db.flush()


def diff_changes(before: dict[str, Any], after: dict[str, Any]) -> list[list[Any]]:
    """[field, before, after] triples for every field whose value changed ("—" for empty)."""

    def show(value: Any) -> str:
        return "—" if value is None or value == "" else str(value)

    out: list[list[Any]] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if show(old) != show(new):
            out.append([key, show(old), show(new)])
    return out


def client_ip(request) -> str | None:
    """Best-effort caller IP (honours X-Forwarded-For set by Render's proxy)."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
