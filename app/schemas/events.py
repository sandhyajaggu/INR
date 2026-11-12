"""Events (frontend: EventsTable.js, AddEventModal.jsx, UploadEventsModal, EventDetailsDrawer, PublicEvents).

The Add/Edit form sends: title, type, status, date (YYYY-MM-DD), time
(HH:MM), venue, mandal, village, liveMeetingLink, prevMeetingLinks
("url1, url2"), prevMeetingLinksList ([{label, url}]), description.
"""

import datetime as dt

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

EVENT_STATUSES = ("Scheduled", "Upcoming", "Completed", "Postponed", "Cancelled")
EVENT_TYPES = (
    "Scheme Distribution", "Village Visit", "Issues", "Public Meeting", "Inauguration", "Review Meeting", "Other",
)


class MeetingLink(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str | None = ""
    url: str


class EventForm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=200, validation_alias=AliasChoices("title", "event_title"))
    type: str = Field(min_length=1, max_length=100, validation_alias=AliasChoices("type", "event_type"))
    status: str = "Scheduled"
    date: dt.date = Field(validation_alias=AliasChoices("date", "event_date"))
    time: dt.time | None = Field(default=None, validation_alias=AliasChoices("time", "event_time"))
    venue: str = Field(min_length=1, max_length=200)
    mandal: str = Field(validation_alias=AliasChoices("mandal", "mandal_name"))
    village: str | None = Field(default=None, validation_alias=AliasChoices("village", "village_name"))
    liveMeetingLink: str | None = Field(default=None, validation_alias=AliasChoices("liveMeetingLink", "live_meeting_link", "live_link"))
    prevMeetingLinks: str | None = None
    prevMeetingLinksList: list[MeetingLink] | None = None
    description: str | None = None
    chief_guest: str | None = None
    attendance: int | None = Field(default=None, ge=0, validation_alias=AliasChoices("attendance", "expected_attendance"))
    photo: str | None = Field(default=None, validation_alias=AliasChoices("photo", "photo_url"))
    # Telugu text for the public website (see app/core/telugu.py). Only the ones sent change; "" clears.
    title_te: str | None = Field(default=None, max_length=300)
    venue_te: str | None = Field(default=None, max_length=300)
    description_te: str | None = None
    chief_guest_te: str | None = Field(default=None, max_length=300)

    @field_validator(
        "title", "type", "venue", "mandal", "village", "liveMeetingLink", "prevMeetingLinks", "description",
        "chief_guest", "photo", "time", "attendance",
        mode="before",
    )
    @classmethod
    def _blank(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("date", mode="before")
    @classmethod
    def _date(cls, v: object) -> object:
        if hasattr(v, "date") and callable(v.date):
            return v.date()
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        if v is None or str(v).strip() == "":
            return "Scheduled"
        for s in EVENT_STATUSES:
            if s.lower() == str(v).strip().lower():
                return s
        raise ValueError(f"status must be one of: {', '.join(EVENT_STATUSES)}")

    def links(self) -> list[dict[str, str]]:
        if self.prevMeetingLinksList:
            return [{"label": (l.label or "").strip(), "url": l.url.strip()} for l in self.prevMeetingLinksList if l.url.strip()]
        if self.prevMeetingLinks:
            return [{"label": "", "url": u.strip()} for u in self.prevMeetingLinks.split(",") if u.strip()]
        return []


EVENT_HEADER_ALIASES = {
    "event_title": "title",
    "event_type": "type",
    "date_(yyyy-mm-dd)": "date",
    "time_(hh:mm)": "time",
    "live_link": "liveMeetingLink",
    "mandal_name": "mandal",
    "village_name": "village",
}
