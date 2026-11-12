"""Dashboard notifications (the bell in AdminNav) and the uploaded-files registry."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    """One notification for one staff user.

    A system event (new public enquiry, war-room alert, admin announcement) is
    fanned out to one row per recipient, so each user has their own read state.
    """

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "is_read", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    page_key: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[str | None] = mapped_column(String(50))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UploadedFile(Base):
    """A file saved through POST /files/upload, so it can be listed, replaced and deleted."""

    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    subfolder: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    original_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
