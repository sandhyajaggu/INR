from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActivityLog(Base):
    """Audit Logs page. One row per sign-in or change.

    `changes` is a list of [field, before, after] triples (what the Audit
    drawer shows). `actor_name` is kept so the log still reads correctly
    after a staff account is deleted.
    """

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    actor_name: Mapped[str | None] = mapped_column(String(150))
    action_type: Mapped[str | None] = mapped_column(String(50))
    module: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[list | None] = mapped_column(JSONB)
    screenshot_url: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
