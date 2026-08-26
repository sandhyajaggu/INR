from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class GalleryPhotoBase(BaseModel):
    title: str | None = None
    category: str | None = Field(
        default=None, pattern="^(leaders|events|spiritual|inaugurations|sports|others)$"
    )
    caption: str | None = None
    status: str = "active"


class GalleryPhotoCreate(GalleryPhotoBase):
    photo_url: str  # obtained from POST /files/upload beforehand


class GalleryPhotoUpdate(GalleryPhotoCreate):
    pass


class GalleryPhotoOut(GalleryPhotoBase, ORMModel):
    id: int
    photo_url: str
    date_added: date
    created_by: int | None


class Mp3SongBase(BaseModel):
    title: str
    description: str | None = None
    status: str = "active"


class Mp3SongCreate(Mp3SongBase):
    file_url: str
    file_name: str | None = None
    duration_seconds: int | None = None


class Mp3SongUpdate(Mp3SongCreate):
    pass


class Mp3SongOut(Mp3SongBase, ORMModel):
    id: int
    file_url: str
    file_name: str | None
    duration_seconds: int | None
    play_count: int
    download_count: int
    date_added: date


class VideoBase(BaseModel):
    title: str
    video_source: str = Field(pattern="^(youtube|upload)$")
    youtube_url: str | None = None
    description: str | None = None
    status: str = "active"


class VideoCreate(VideoBase):
    video_file_url: str | None = None  # required when video_source == 'upload'


class VideoUpdate(VideoCreate):
    pass


class VideoOut(VideoBase, ORMModel):
    id: int
    video_file_url: str | None
    upload_date: date


class PressGalleryBase(BaseModel):
    title: str
    caption: str | None = None
    status: str = "active"


class PressGalleryCreate(PressGalleryBase):
    photo_url: str | None = None


class PressGalleryUpdate(PressGalleryCreate):
    pass


class PressGalleryOut(PressGalleryBase, ORMModel):
    id: int
    photo_url: str | None
    date_added: date
