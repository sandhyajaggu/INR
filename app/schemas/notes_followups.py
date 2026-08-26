from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, validate_epic_no


class NoteFollowupCreate(BaseModel):
    subject: str | None = None
    related_person: str | None = None
    epic_no: str | None = None
    mobile_number: str | None = None
    category: str | None = None
    priority: str | None = Field(default=None, pattern="^(low|medium|high)$")
    due_date: date | None = None
    status: str = Field(default="open", pattern="^(open|in_progress|closed)$")
    village_name: str | None = None
    mandal_name: str | None = None
    notes_description: str | None = None

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: str | None) -> str | None:
        return validate_epic_no(v)


class NoteFollowupUpdate(NoteFollowupCreate):
    pass


class NoteFollowupOut(ORMModel):
    id: int
    subject: str | None
    related_person: str | None
    epic_no: str | None
    mobile_number: str | None
    category: str | None
    priority: str | None
    due_date: date | None
    status: str
    village_id: int | None
    mandal_id: int | None
    notes_description: str | None
    voter_id: int | None
    created_by: int | None
    created_at: datetime
