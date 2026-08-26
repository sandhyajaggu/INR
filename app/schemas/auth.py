from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class CaptchaResponse(BaseModel):
    question: str
    captcha_token: str


class LoginRequest(BaseModel):
    role: str = Field(..., pattern="^(super_admin|admin)$")
    email: EmailStr
    password: str
    captcha_token: str
    captcha_answer: str


class TokenResponse(BaseModel):
    message: str = "Login successful"
    name: str
    role: str
    access_token: str
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    detail: str
    reset_token: str


class CurrentUserResponse(ORMModel):
    id: int
    name: str
    email: str
    role: str
    mobile: str | None
    status: str
