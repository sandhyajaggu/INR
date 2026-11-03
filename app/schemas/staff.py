"""User Management (frontend: SuperAdminUserManagement.jsx / UserFormModal.jsx).

Request and response fields use the frontend's names: epic, role (the role
label, e.g. "Booth Agent"), photo, scope, access, status ("Active" /
"Inactive"), lastLoginAt (epoch milliseconds), mustChangePassword, login.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.access import USER_ROLES
from app.schemas.common import validate_epic_no, validate_mobile_number

ACCESS_LEVELS = {"none", "view", "download", "edit", "admin"}


class _UserFields(BaseModel):
    epic: str | None = None
    name: str = Field(min_length=1, max_length=150)
    status: str = Field(default="Active", pattern="^(Active|Inactive)$")
    mobile: str
    email: EmailStr | None = None
    mandal: str = Field(min_length=1)
    village: str = Field(min_length=1)
    address: str = Field(min_length=1)
    photo: str | None = None
    role: str
    scope: str | None = None
    access: dict[str, str] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("epic")
    @classmethod
    def _epic(cls, value: str | None) -> str | None:
        return validate_epic_no(value)

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, value: str) -> str:
        return validate_mobile_number(value)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in USER_ROLES:
            raise ValueError(f"role must be one of: {', '.join(USER_ROLES)}")
        return value

    @field_validator("access")
    @classmethod
    def _access(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        bad = {k: v for k, v in value.items() if v not in ACCESS_LEVELS}
        if bad:
            raise ValueError(f"access levels must be one of {sorted(ACCESS_LEVELS)}; got {bad}")
        return value


class UserCreate(_UserFields):
    pass


class UserUpdate(_UserFields):
    pass


class UserOut(BaseModel):
    id: str
    name: str
    epic: str | None
    role: str
    mobile: str | None
    email: str | None
    mandal: str | None
    village: str | None
    address: str | None
    photo: str | None
    scope: str | None
    access: dict[str, str]
    status: str
    lastLoginAt: int | None
    mustChangePassword: bool
    login: str


class UserCreatedOut(UserOut):
    temporaryPassword: str


class ResetPasswordOut(BaseModel):
    temporaryPassword: str


class SuccessOut(BaseModel):
    success: bool = True
