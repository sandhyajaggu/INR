from typing import Any

from pydantic import BaseModel, EmailStr, Field


class CaptchaResponse(BaseModel):
    question: str
    captcha_token: str


class LoginRequest(BaseModel):
    # Login.js offers super_admin / admin / staff. "staff" covers every other
    # User Management role (Booth Agent, Mandal In-Charge, Custom, ...).
    role: str = Field(..., pattern="^(super_admin|admin|staff)$")
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
    # Stored by Login.js as localStorage.currentUser: id, name, epic, role
    # (super_admin/admin/staff), displayRole, email, mandal, village, scope,
    # access (page map), photo, ...
    user: dict[str, Any]


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    detail: str
    reset_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
