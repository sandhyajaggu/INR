from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog


async def log_activity(
    db: AsyncSession,
    *,
    actor_id: int | None,
    action_type: str,
    module: str,
    reference_id: int | None,
    description: str,
    commit: bool = False,
) -> None:
    """Reusable activity-log writer.

    Called from services for voters, development_works, beneficiaries, and
    CM Relief Fund on every create/update/delete, per the spec. Not committed
    by default — call sites that already manage a transaction can flush it
    alongside their own commit; pass commit=True for a standalone call.
    """
    entry = ActivityLog(
        actor_id=actor_id,
        action_type=action_type,
        module=module,
        reference_id=reference_id,
        description=description,
    )
    db.add(entry)
    if commit:
        await db.commit()
    else:
        await db.flush()
