"""Development Works (frontend: Development.js, AddDevelopmentWorkModal, UploadWorksModal,
DevelopmentDetailsDrawer, PublicAttainments).

The Add/Edit form sends:
    name, category, fund_source, mandal, village, budget, contractor,
    start_date, completion_date, progress, status ("Not Started" /
    "In Progress" / "Completed"), remarks, photo, completed_photo
"""

from datetime import date
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import coerce_excel_cell_to_str

DEV_STATUSES = ("Not Started", "In Progress", "Completed")
_LEGACY_STATUS = {"pending": "Not Started", "in_progress": "In Progress", "completed": "Completed"}


def _blank(v: object) -> object:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class DevelopmentWorkCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # The Add/Edit form needs a completion photo for a Completed work; uploads don't.
    _require_completed_photo: bool = True

    name: str = Field(min_length=1, max_length=255, validation_alias=AliasChoices("name", "title", "work_name"))
    category: str | None = None
    fund_source: str | None = None
    mandal: str = Field(validation_alias=AliasChoices("mandal", "mandal_name"))
    village: str | None = Field(default=None, validation_alias=AliasChoices("village", "village_name"))
    budget: Decimal = Field(ge=0, validation_alias=AliasChoices("budget", "estimated_cost", "sanctioned_budget"))
    contractor: str | None = None
    contractor_te: str | None = None
    start_date: date | None = Field(default=None, validation_alias=AliasChoices("start_date", "work_date"))
    completion_date: date | None = None
    progress: int = Field(default=0, ge=0, le=100)
    status: str = "Not Started"
    remarks: str | None = Field(default=None, validation_alias=AliasChoices("remarks", "description"))
    photo: str | None = Field(default=None, validation_alias=AliasChoices("photo", "photo_url"))
    completed_photo: str | None = Field(default=None, validation_alias=AliasChoices("completed_photo", "completed_photo_url"))
    # Telugu text for the public website (see app/core/telugu.py). Only the ones sent change; "" clears.
    name_te: str | None = Field(default=None, max_length=400)
    remarks_te: str | None = None

    @field_validator(
        "category", "fund_source", "village", "contractor", "contractor_te", "remarks", "photo", "completed_photo",
        "start_date", "completion_date", "mandal", "name",
        mode="before",
    )
    @classmethod
    def _clean(cls, v: object) -> object:
        return _blank(coerce_excel_cell_to_str(v) if not hasattr(v, "year") else v)

    @field_validator("budget", "progress", mode="before")
    @classmethod
    def _number(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.replace(",", "").replace("₹", "").replace("%", "").strip()
            return v or 0
        return 0 if v is None else v

    @field_validator("start_date", "completion_date", mode="before")
    @classmethod
    def _date(cls, v: object) -> object:
        if hasattr(v, "date") and callable(v.date):
            return v.date()
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        v = _blank(v)
        if v is None:
            return "Not Started"
        text = str(v).strip()
        text = _LEGACY_STATUS.get(text.lower(), text)
        for s in DEV_STATUSES:
            if s.lower() == text.lower():
                return s
        raise ValueError("status must be Not Started, In Progress or Completed")

    @model_validator(mode="after")
    def _completed_rules(self) -> "DevelopmentWorkCreate":
        if self.status == "Completed":
            if self.completion_date is None:
                raise ValueError("completion_date is required when status is Completed")
            if self._require_completed_photo and not self.completed_photo:
                raise ValueError("completed_photo is required when status is Completed")
            self.progress = 100
        if self.completion_date and self.start_date and self.completion_date < self.start_date:
            raise ValueError("completion_date can't be before start_date")
        return self


class DevelopmentWorkUpdate(DevelopmentWorkCreate):
    pass


class DevelopmentWorkBulkRow(DevelopmentWorkCreate):
    """Upload rows: same rules, except a Completed work's photo is added later by editing."""

    _require_completed_photo: bool = False


DEV_HEADER_ALIASES = {
    "work_name": "name",
    "title": "name",
    "sanctioned_budget_(₹)": "budget",
    "sanctioned_budget_(rs)": "budget",
    "sanctioned_budget": "budget",
    "progress_%": "progress",
    "progress_(%)": "progress",
    "mandal_name": "mandal",
    "village_name": "village",
}


class DevelopmentStatusSummary(BaseModel):
    status: str
    total: int
