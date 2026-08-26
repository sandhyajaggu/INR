import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
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
from app.schemas.auth import LoginRequest, TokenResponse


async def authenticate(db: AsyncSession, payload: LoginRequest) -> TokenResponse:
    if not verify_captcha(payload.captcha_token, payload.captcha_answer):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect or expired CAPTCHA answer")

    stmt = select(StaffUser).where(StaffUser.email == payload.email, StaffUser.role == payload.role)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    return TokenResponse(
        message="Login successful",
        name=user.name,
        role=user.role,
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
    )


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    user = await db.get(StaffUser, int(payload["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    return TokenResponse(
        message="Token refreshed",
        name=user.name,
        role=user.role,
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id, user.role),
    )


async def issue_password_reset_token(db: AsyncSession, email: str) -> str:
    """Stub: returns a one-time reset token. Email delivery is wired up later."""
    stmt = select(StaffUser).where(StaffUser.email == email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        # Do not reveal whether the email exists.
        return secrets.token_urlsafe(32)
    return secrets.token_urlsafe(32)


def make_password_hash(plain_password: str) -> str:
    return hash_password(plain_password)
