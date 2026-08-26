from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.core.security import generate_captcha
from app.schemas.auth import (
    CaptchaResponse,
    CurrentUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.auth_service import authenticate, issue_password_reset_token, refresh_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/captcha", response_model=CaptchaResponse, summary="Get a math CAPTCHA challenge")
async def get_captcha() -> CaptchaResponse:
    question, token = generate_captcha()
    return CaptchaResponse(question=question, captcha_token=token)


@router.post("/login", response_model=TokenResponse, summary="Log in as super_admin or admin")
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    return await authenticate(db, payload)


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
    return ForgotPasswordResponse(detail="If that email exists, a reset token has been issued.", reset_token=reset_token)


@router.get("/me", response_model=CurrentUserResponse, summary="Get the current authenticated staff user")
async def read_current_user(current_user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)
