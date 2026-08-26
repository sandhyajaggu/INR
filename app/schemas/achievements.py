from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class AchievementBase(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    status: str = "active"


class AchievementCreate(AchievementBase):
    photo_url: str | None = None


class AchievementUpdate(AchievementCreate):
    pass


class AchievementOut(AchievementBase, ORMModel):
    id: int
    photo_url: str | None
    created_at: datetime
