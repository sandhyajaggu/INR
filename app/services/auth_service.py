import re
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_captcha,
    verify_password,
)
from app.models.staff import StaffUser
from app.schemas.common import MOBILE_PATTERN
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.activity_service import log_activity
from app.services.user_service import serialize_session_user


def normalize_mobile(value: str) -> str | None:
    """'+91 98493 55955', '098493-55955', '9849355955' -> '9849355955'; None if not a mobile number."""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if MOBILE_PATTERN.match(digits) else None


def users_by_identifier_stmt(identifier: str):
    """SELECT staff users whose email (if it has '@') or mobile number matches `identifier`."""
    identifier = identifier.strip()
    if "@" in identifier:
        return select(StaffUser).where(func.lower(StaffUser.email) == identifier.lower())
    mobile = normalize_mobile(identifier)
    if mobile is None:
        return None
    stored = func.right(func.regexp_replace(func.coalesce(StaffUser.mobile, ""), r"\D", "", "g"), 10)
    return select(StaffUser).where(stored == mobile).order_by(StaffUser.id)


def _token_response(user: StaffUser, message: str) -> TokenResponse:
    return TokenResponse(
        message=message,
        name=user.name,
        role=user.role,
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
        user=serialize_session_user(user),
    )


async def authenticate(db: AsyncSession, payload: LoginRequest, ip_address: str | None = None) -> TokenResponse:
    if not verify_captcha(payload.captcha_token, payload.captcha_answer):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect or expired CAPTCHA answer")

    stmt = users_by_identifier_stmt(payload.identifier)
    candidates = (await db.execute(stmt.where(StaffUser.role == payload.role))).scalars().all() if stmt is not None else []
    # A mobile number isn't unique across accounts: sign in to the one whose password matches.
    user = next(
        (u for u in candidates if u.status == "active" and verify_password(payload.password, u.password_hash)),
        None,
    )
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    user.last_login_at = datetime.now(timezone.utc)
    await log_activity(
        db,
        actor_id=user.id,
        actor_name=user.name,
        action_type="signed_in",
        module="Auth",
        reference_id=user.id,
        description="Signed in",
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(user)
    return _token_response(user, "Login successful")


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    user = await db.get(StaffUser, int(payload["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    return _token_response(user, "Token refreshed")


async def issue_password_reset_token(db: AsyncSession, identifier: str) -> str:
    """Stub: returns a one-time reset token. Email/SMS delivery is wired up later.

    `identifier` is an email or mobile number (the login `username`).
    """
    stmt = users_by_identifier_stmt(identifier)
    if stmt is not None:
        (await db.execute(stmt)).scalars().first()
    # Same response whether or not the account exists, so it can't be probed.
    return secrets.token_urlsafe(32)


async def change_password(db: AsyncSession, user: StaffUser, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await log_activity(
        db,
        actor_id=user.id,
        action_type="password_changed",
        module="Auth",
        reference_id=user.id,
        description="Changed own password",
    )
    await db.commit()


def make_password_hash(plain_password: str) -> str:
    return hash_password(plain_password)
