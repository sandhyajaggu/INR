from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator


class CaptchaResponse(BaseModel):
    question: str
    captcha_token: str


class _UsernameOrEmail(BaseModel):
    """`username` takes an email or a 10-digit mobile number (like the YSR site).

    `email` is still accepted so the current Login.js keeps working; send one of the two.
    """

    username: str | None = Field(default=None, max_length=150, description="Email or mobile number")
    email: EmailStr | None = None

    @model_validator(mode="after")
    def _need_one(self):
        if not (self.username and self.username.strip()) and not self.email:
            raise ValueError("Enter your email or mobile number")
        return self

    @property
    def identifier(self) -> str:
        return (self.username or "").strip() or str(self.email)


class LoginRequest(_UsernameOrEmail):
    # Login.js offers super_admin / admin / staff. "staff" covers every other
    # User Management role (Booth Agent, Mandal In-Charge, Custom, ...).
    role: str = Field(..., pattern="^(super_admin|admin|staff)$")
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


class ForgotPasswordRequest(_UsernameOrEmail):
    pass


class ForgotPasswordResponse(BaseModel):
    message: str
    detail: str
    reset_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
