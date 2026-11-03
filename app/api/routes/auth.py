from typing import Any

from fastapi import APIRouter, Request

from app.core.dependencies import CurrentUser, DbSession
from app.core.security import generate_captcha
from app.schemas.auth import (
    CaptchaResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.activity_service import client_ip
from app.services.auth_service import (
    authenticate,
    change_password,
    issue_password_reset_token,
    refresh_access_token,
)
from app.services.user_service import serialize_session_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/captcha", response_model=CaptchaResponse, summary="Get a math CAPTCHA challenge")
async def get_captcha() -> CaptchaResponse:
    question, token = generate_captcha()
    return CaptchaResponse(question=question, captcha_token=token)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in as super_admin, admin or staff",
    description="Returns access/refresh tokens plus the `user` object (with its page `access` map).",
)
async def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    return await authenticate(db, payload, ip_address=client_ip(request))


@router.post("/refresh", response_model=TokenResponse, summary="Exchange a refresh token for a new pair")
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    return await refresh_access_token(db, payload.refresh_token)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset token",
    description="Stub for now: returns a reset token directly. Email delivery is wired up later.",
)
async def forgot_password(payload: ForgotPasswordRequest, db: DbSession) -> ForgotPasswordResponse:
    reset_token = await issue_password_reset_token(db, payload.email)
    message = f"Password reset instructions sent to {payload.email}"
    return ForgotPasswordResponse(message=message, detail=message, reset_token=reset_token)


@router.post(
    "/change-password",
    summary="Change own password (clears the first-sign-in flag)",
)
async def change_own_password(
    payload: ChangePasswordRequest, db: DbSession, current_user: CurrentUser
) -> dict[str, Any]:
    await change_password(db, current_user, payload.current_password, payload.new_password)
    return {"success": True}


@router.get("/me", summary="Get the current signed-in user (same shape as login's `user`)")
async def read_current_user(current_user: CurrentUser) -> dict[str, Any]:
    return serialize_session_user(current_user)
