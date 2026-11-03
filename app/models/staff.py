from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StaffUser(Base):
    """A dashboard user account (User Management page).

    `role` is the login role (super_admin / admin / staff) used for sign-in
    and tokens. `display_role` is the role label picked in the User
    Management form ("Booth Agent", "Mandal In-Charge", "Custom", ...).
    `access` is the per-page permission map {page_key: none|view|download|edit|admin}.
    """

    __tablename__ = "staff_users"
    __table_args__ = (
        CheckConstraint("role IN ('super_admin','admin','staff')", name="ck_staff_users_role"),
        CheckConstraint("status IN ('active','inactive')", name="ck_staff_users_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    display_role: Mapped[str | None] = mapped_column(String(50))
    mobile: Mapped[str | None] = mapped_column(String(15))
    epic_no: Mapped[str | None] = mapped_column(String(20))
    mandal: Mapped[str | None] = mapped_column(String(100))
    village: Mapped[str | None] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(String(100))
    access: Mapped[dict | None] = mapped_column(JSONB)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
