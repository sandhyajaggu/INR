"""Import every model here so Base.metadata (and Alembic autogenerate) sees all tables."""

from app.models.achievements import Achievement
from app.models.activity_log import ActivityLog
from app.models.contact import ContactMessage
from app.models.development_works import DevelopmentWork
from app.models.events import Event
from app.models.geography import Booth, Mandal, Village
from app.models.janata_darbar import JanataDarbarVisit
from app.models.local_leaders import LocalLeader
from app.models.multimedia import GalleryPhoto, Mp3Song, PressGalleryItem, Video
from app.models.notes_followups import NoteFollowup
from app.models.schemes import Beneficiary, Scheme
from app.models.settings import AppSettings
from app.models.staff import StaffUser
from app.models.surveys import Survey
from app.models.voters import Voter

__all__ = [
    "Achievement",
    "ActivityLog",
    "AppSettings",
    "Beneficiary",
    "Booth",
    "ContactMessage",
    "DevelopmentWork",
    "Event",
    "GalleryPhoto",
    "JanataDarbarVisit",
    "LocalLeader",
    "Mandal",
    "Mp3Song",
    "NoteFollowup",
    "PressGalleryItem",
    "Scheme",
    "StaffUser",
    "Survey",
    "Video",
    "Village",
    "Voter",
]
