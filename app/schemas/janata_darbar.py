from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, validate_epic_no


class JanataDarbarCreate(BaseModel):
    visitor_name: str
    mobile_number: str | None = None
    epic_no: str | None = None
    age: int | None = None
    gender: str | None = None
    issue_category: str | None = None
    village_name: str | None = None
    mandal_name: str | None = None
    visit_date: date | None = None
    status: str = Field(default="pending", pattern="^(pending|in_progress|resolved|referred)$")
    issue_description: str | None = None
    action_taken: str | None = None
    document_url: str | None = None

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: str | None) -> str | None:
        return validate_epic_no(v)


class JanataDarbarUpdate(JanataDarbarCreate):
    pass


class JanataDarbarOut(ORMModel):
    id: int
    token_number: str
    visitor_name: str
    mobile_number: str | None
    epic_no: str | None
    age: int | None
    gender: str | None
    issue_category: str | None
    village_id: int | None
    mandal_id: int | None
    visit_date: date | None
    status: str
    issue_description: str | None
    action_taken: str | None
    voter_id: int | None
    document_url: str | None
