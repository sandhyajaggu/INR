from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class StaffCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(super_admin|admin)$")
    mobile: str | None = None
    status: str = "active"


class StaffUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8)
    role: str | None = Field(default=None, pattern="^(super_admin|admin)$")
    mobile: str | None = None
    status: str | None = None


class StaffOut(ORMModel):
    id: int
    name: str
    email: str
    role: str
    mobile: str | None
    status: str
    created_at: datetime
    updated_at: datetime
