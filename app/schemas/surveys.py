from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, validate_epic_no


class SurveyCreate(BaseModel):
    respondent_name: str | None = None
    mobile_number: str | None = None
    epic_no: str | None = None
    category: str | None = None
    feedback_type: str | None = None
    satisfaction_rating: int | None = Field(default=None, ge=1, le=5)
    village_name: str | None = None
    mandal_name: str | None = None
    survey_date: date | None = None
    status: str = "pending"
    feedback_details: str | None = None
    photo_url: str | None = None

    @field_validator("epic_no", mode="before")
    @classmethod
    def _validate_epic_no(cls, v: str | None) -> str | None:
        return validate_epic_no(v)


class SurveyUpdate(SurveyCreate):
    pass


class SurveyOut(ORMModel):
    id: int
    respondent_name: str | None
    mobile_number: str | None
    epic_no: str | None
    category: str | None
    feedback_type: str | None
    satisfaction_rating: int | None
    village_id: int | None
    mandal_id: int | None
    survey_date: date | None
    status: str
    feedback_details: str | None
    voter_id: int | None
    photo_url: str | None
    created_by: int | None
