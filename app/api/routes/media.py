"""Media & Gallery page (frontend: Media.jsx, MediaModals.jsx, PublicMedia.jsx, mockMediaApi).

    GET    /media                          getAll() -> {pressMeets, gallery, videos, mp3, mp4}
    POST   /media/press-meets              createPressMeet {title, description, date, url, image}
    PUT    /media/press-meets/{id}         updatePressMeet
    DELETE /media/press-meets/{id}         deletePressMeet
    POST   /media/albums                   create album {title, date, cover, photos?}
    PUT    /media/albums/{id}              edit album {title, date, cover}
    POST   /media/albums/{id}/photos       addPhotosToAlbum(albumId, photos[])
    DELETE /media/albums/{id}/photos       remove one photo {url}
    DELETE /media/albums/{id}
    POST   /media/videos                   createVideo {title, date, url, thumbnail}  (YouTube)
    PUT    /media/videos/{id}              updateVideo
    DELETE /media/videos/{id}
    POST   /media/mp3                      createMP3 {title, date, duration, size, file_url}
    PUT    /media/mp3/{id}                 edit {title, date, duration}
    DELETE /media/mp3/{id}
    POST   /media/mp4                      createMP4 {title, date, duration, size, file_url, thumbnail}
    PUT    /media/mp4/{id}
    DELETE /media/mp4/{id}
    GET    /public/media?lang=te           same as GET /media, no sign-in (public website); lang=te -> Telugu titles

Every form also takes title_te (press meets and videos: description_te too); rows return them.

Deletes return {"success": true}. Files themselves go through POST /files/upload.
"""

import re
import datetime as dt
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.core.dependencies import DbSession, page_access
from app.core.ids import format_id, parse_id
from app.models.engagement import MediaAlbum
from app.models.multimedia import Mp3Song, PressGalleryItem, Video
from app.core.telugu import LangQuery, apply_te, localize_all, te_keys, te_updates
from app.services.activity_service import log_activity

router = APIRouter(prefix="/media", tags=["Media & Gallery"])
public_router = APIRouter(prefix="/public", tags=["Public"])

CanView = page_access("media_gallery", "view")
CanEdit = page_access("media_gallery", "edit")
CanDelete = page_access("media_gallery", "admin")

_YT_PATTERNS = (r"[?&]v=([\w-]{6,})", r"youtu\.be/([\w-]{6,})", r"youtube\.com/(?:embed|shorts|live)/([\w-]{6,})")


def youtube_id(url: str | None) -> str | None:
    for pattern in _YT_PATTERNS:
        m = re.search(pattern, url or "")
        if m:
            return m.group(1)
    return None


def _date_fields(d: date | None) -> dict[str, str | None]:
    return {"date": d.strftime("%d %b %Y") if d else None, "date_raw": d.isoformat() if d else None}


def _seconds(duration: str | None) -> int | None:
    if not duration:
        return None
    parts = [p for p in duration.split(":") if p.strip().isdigit()]
    if not parts:
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


MEDIA_TE = ("title", "description")


class _MediaBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=200)
    date: dt.date | None = None
    # Telugu for the public website (app/core/telugu.py). Only sent keys change; "" clears.
    title_te: str | None = Field(default=None, max_length=300)

    @field_validator("date", mode="before")
    @classmethod
    def _blank_date(cls, v: object) -> object:
        return None if v in ("", None) else v


class PressMeetForm(_MediaBase):
    description: str | None = None
    description_te: str | None = None
    url: str | None = None
    image: str | None = None


class AlbumForm(_MediaBase):
    cover: str | None = None
    photos: list[str] | None = None


class AlbumPhotos(BaseModel):
    photos: list[str] = Field(min_length=1)


class AlbumPhotoRemove(BaseModel):
    url: str


class VideoForm(_MediaBase):
    url: str = Field(min_length=1)
    thumbnail: str | None = None
    channel: str | None = None
    description_te: str | None = None


class AudioForm(_MediaBase):
    duration: str | None = None
    size: str | None = None
    file_url: str | None = None


class Mp4Form(AudioForm):
    thumbnail: str | None = None


def press_row(p: PressGalleryItem) -> dict[str, Any]:
    vid = youtube_id(p.video_url)
    return {
        "id": format_id("PM", p.id),
        "title": p.title,
        "description": p.caption,
        **_date_fields(p.date_added),
        "url": p.video_url,
        "image": p.photo_url or (f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else None),
        **te_keys(p.te, MEDIA_TE),
    }


def album_row(a: MediaAlbum) -> dict[str, Any]:
    photos = a.photos or []
    return {
        "id": format_id("GAL", a.id),
        "title": a.title,
        **_date_fields(a.album_date),
        "cover": a.cover_url or (photos[0] if photos else None),
        "photos_count": len(photos),
        "photos": photos,
        **te_keys(a.te, ("title",)),
    }


def video_row(v: Video) -> dict[str, Any]:
    vid = youtube_id(v.youtube_url)
    return {
        "id": format_id("VID", v.id),
        "title": v.title,
        **_date_fields(v.upload_date),
        "source": "YouTube",
        "channel": v.channel or "INR Official",
        "url": v.youtube_url,
        "embed_id": vid,
        "thumbnail": v.thumbnail_url or (f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else None),
        "description": v.description,
        **te_keys(v.te, MEDIA_TE),
    }


def mp3_row(m: Mp3Song) -> dict[str, Any]:
    return {
        "id": format_id("MP3", m.id),
        "title": m.title,
        "type": "MP3 audio",
        **_date_fields(m.date_added),
        "duration": m.duration,
        "size": m.file_size,
        "file_url": m.file_url,
        "play_count": m.play_count,
        "download_count": m.download_count,
        **te_keys(m.te, ("title",)),
    }


def mp4_row(v: Video) -> dict[str, Any]:
    return {
        "id": format_id("MP4", v.id),
        "title": v.title,
        "type": "MP4 video",
        **_date_fields(v.upload_date),
        "duration": v.duration,
        "size": v.file_size,
        "thumbnail": v.thumbnail_url,
        "file_url": v.video_file_url,
        **te_keys(v.te, ("title",)),
    }


async def all_media(db) -> dict[str, list[dict[str, Any]]]:
    press = (await db.execute(select(PressGalleryItem).where(PressGalleryItem.status == "active")
                              .order_by(PressGalleryItem.date_added.desc(), PressGalleryItem.id.desc()))).scalars().all()
    albums = (await db.execute(select(MediaAlbum).order_by(MediaAlbum.album_date.desc().nulls_last(), MediaAlbum.id.desc()))).scalars().all()
    videos = (await db.execute(select(Video).where(Video.status == "active")
                               .order_by(Video.upload_date.desc(), Video.id.desc()))).scalars().all()
    mp3 = (await db.execute(select(Mp3Song).where(Mp3Song.status == "active")
                            .order_by(Mp3Song.date_added.desc(), Mp3Song.id.desc()))).scalars().all()
    return {
        "pressMeets": [press_row(p) for p in press],
        "gallery": [album_row(a) for a in albums],
        "videos": [video_row(v) for v in videos if v.video_source == "youtube"],
        "mp3": [mp3_row(m) for m in mp3],
        "mp4": [mp4_row(v) for v in videos if v.video_source == "upload"],
    }


async def _get(db, model, item_id: str, label: str, *, source: str | None = None):
    obj = await db.get(model, parse_id(item_id, label=label), populate_existing=True)
    if obj is None or (source and getattr(obj, "video_source", None) != source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return obj


async def _log(db, user, action: str, description: str, ref: int | None) -> None:
    await log_activity(
        db, actor_id=user.id, action_type=action, module="Media", reference_id=ref, description=description
    )


@router.get("", summary="All media (press meets, albums, videos, MP3, MP4)")
async def get_media(db: DbSession, current_user: CanView) -> dict[str, list[dict[str, Any]]]:
    return await all_media(db)


@public_router.get("/media", summary="All media for the public website (unauthenticated); ?lang=te for Telugu")
async def get_public_media(db: DbSession, lang: LangQuery = "en") -> dict[str, list[dict[str, Any]]]:
    return {group: localize_all(rows, lang, MEDIA_TE) for group, rows in (await all_media(db)).items()}


# --- press meets ----------------------------------------------------------------


def _apply_press(obj: PressGalleryItem, form: PressMeetForm) -> None:
    obj.title = form.title
    obj.caption = form.description
    obj.video_url = form.url
    obj.photo_url = form.image
    if form.date:
        obj.date_added = form.date


@router.post("/press-meets", status_code=status.HTTP_201_CREATED, summary="Add a press meet")
async def create_press_meet(payload: PressMeetForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = PressGalleryItem(title=payload.title)
    _apply_press(obj, payload)
    db.add(obj)
    await db.flush()
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "press_meet_added", f"Added press meet {obj.title}", obj.id)
    await db.commit()
    return press_row(await _get(db, PressGalleryItem, str(obj.id), "Press meet"))


@router.put("/press-meets/{item_id}", summary="Edit a press meet")
async def update_press_meet(item_id: str, payload: PressMeetForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, PressGalleryItem, item_id, "Press meet")
    _apply_press(obj, payload)
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "press_meet_updated", f"Updated press meet {obj.title}", obj.id)
    await db.commit()
    return press_row(await _get(db, PressGalleryItem, item_id, "Press meet"))


@router.delete("/press-meets/{item_id}", summary="Delete a press meet")
async def delete_press_meet(item_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, PressGalleryItem, item_id, "Press meet")
    await _log(db, current_user, "press_meet_deleted", f"Deleted press meet {obj.title}", obj.id)
    await db.delete(obj)
    await db.commit()
    return {"success": True}


# --- albums ------------------------------------------------------------------------


@router.post("/albums", status_code=status.HTTP_201_CREATED, summary="Create a photo album")
async def create_album(payload: AlbumForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = MediaAlbum(
        title=payload.title, album_date=payload.date or date.today(), cover_url=payload.cover or None,
        photos=payload.photos or [], created_by=current_user.id,
    )
    db.add(obj)
    await db.flush()
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "album_added", f"Created album {obj.title}", obj.id)
    await db.commit()
    return album_row(await _get(db, MediaAlbum, str(obj.id), "Album"))


@router.put("/albums/{album_id}", summary="Edit an album (title, date, cover)")
async def update_album(album_id: str, payload: AlbumForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, MediaAlbum, album_id, "Album")
    obj.title = payload.title
    if payload.date:
        obj.album_date = payload.date
    obj.cover_url = payload.cover or obj.cover_url
    if payload.photos is not None:
        obj.photos = payload.photos
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "album_updated", f"Updated album {obj.title}", obj.id)
    await db.commit()
    return album_row(await _get(db, MediaAlbum, album_id, "Album"))


@router.post("/albums/{album_id}/photos", summary="Add photos to an album")
async def add_album_photos(album_id: str, payload: AlbumPhotos, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, MediaAlbum, album_id, "Album")
    obj.photos = [*(obj.photos or []), *[p for p in payload.photos if p]]
    if not obj.cover_url and obj.photos:
        obj.cover_url = obj.photos[0]
    await _log(db, current_user, "album_photos_added", f"Added {len(payload.photos)} photos to {obj.title}", obj.id)
    await db.commit()
    return album_row(await _get(db, MediaAlbum, album_id, "Album"))


@router.delete("/albums/{album_id}/photos", summary="Remove one photo from an album")
async def remove_album_photo(album_id: str, payload: AlbumPhotoRemove, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, MediaAlbum, album_id, "Album")
    obj.photos = [p for p in (obj.photos or []) if p != payload.url]
    await db.commit()
    return album_row(await _get(db, MediaAlbum, album_id, "Album"))


@router.delete("/albums/{album_id}", summary="Delete an album")
async def delete_album(album_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, MediaAlbum, album_id, "Album")
    await _log(db, current_user, "album_deleted", f"Deleted album {obj.title}", obj.id)
    await db.delete(obj)
    await db.commit()
    return {"success": True}


# --- YouTube videos -------------------------------------------------------------------


def _apply_video(obj: Video, form: VideoForm) -> None:
    if youtube_id(form.url) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "url must be a YouTube link")
    obj.title = form.title
    obj.youtube_url = form.url
    obj.thumbnail_url = form.thumbnail or None
    obj.channel = form.channel or obj.channel
    if form.date:
        obj.upload_date = form.date


@router.post("/videos", status_code=status.HTTP_201_CREATED, summary="Add a YouTube video")
async def create_video(payload: VideoForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = Video(title=payload.title, video_source="youtube")
    _apply_video(obj, payload)
    db.add(obj)
    await db.flush()
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "video_added", f"Added video {obj.title}", obj.id)
    await db.commit()
    return video_row(await _get(db, Video, str(obj.id), "Video"))


@router.put("/videos/{video_id}", summary="Edit a YouTube video")
async def update_video(video_id: str, payload: VideoForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, Video, video_id, "Video", source="youtube")
    _apply_video(obj, payload)
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "video_updated", f"Updated video {obj.title}", obj.id)
    await db.commit()
    return video_row(await _get(db, Video, video_id, "Video"))


@router.delete("/videos/{video_id}", summary="Delete a YouTube video")
async def delete_video(video_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, Video, video_id, "Video", source="youtube")
    await _log(db, current_user, "video_deleted", f"Deleted video {obj.title}", obj.id)
    await db.delete(obj)
    await db.commit()
    return {"success": True}


# --- MP3 ---------------------------------------------------------------------------------


@router.post("/mp3", status_code=status.HTTP_201_CREATED, summary="Add an MP3")
async def create_mp3(payload: AudioForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = Mp3Song(
        title=payload.title, file_url=payload.file_url, duration=payload.duration,
        duration_seconds=_seconds(payload.duration), file_size=payload.size,
    )
    if payload.date:
        obj.date_added = payload.date
    db.add(obj)
    await db.flush()
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "mp3_added", f"Added MP3 {obj.title}", obj.id)
    await db.commit()
    return mp3_row(await _get(db, Mp3Song, str(obj.id), "MP3"))


@router.put("/mp3/{item_id}", summary="Edit an MP3 (title, date, duration)")
async def update_mp3(item_id: str, payload: AudioForm, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, Mp3Song, item_id, "MP3")
    obj.title = payload.title
    if payload.date:
        obj.date_added = payload.date
    if payload.duration is not None:
        obj.duration = payload.duration
        obj.duration_seconds = _seconds(payload.duration)
    if payload.size is not None:
        obj.file_size = payload.size
    if payload.file_url:
        obj.file_url = payload.file_url
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "mp3_updated", f"Updated MP3 {obj.title}", obj.id)
    await db.commit()
    return mp3_row(await _get(db, Mp3Song, item_id, "MP3"))


@router.delete("/mp3/{item_id}", summary="Delete an MP3")
async def delete_mp3(item_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, Mp3Song, item_id, "MP3")
    await _log(db, current_user, "mp3_deleted", f"Deleted MP3 {obj.title}", obj.id)
    await db.delete(obj)
    await db.commit()
    return {"success": True}


# --- MP4 downloads -------------------------------------------------------------------------


@router.post("/mp4", status_code=status.HTTP_201_CREATED, summary="Add an MP4 download")
async def create_mp4(payload: Mp4Form, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = Video(
        title=payload.title, video_source="upload", video_file_url=payload.file_url, duration=payload.duration,
        file_size=payload.size, thumbnail_url=payload.thumbnail,
    )
    if payload.date:
        obj.upload_date = payload.date
    db.add(obj)
    await db.flush()
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "mp4_added", f"Added MP4 {obj.title}", obj.id)
    await db.commit()
    return mp4_row(await _get(db, Video, str(obj.id), "MP4"))


@router.put("/mp4/{item_id}", summary="Edit an MP4 download")
async def update_mp4(item_id: str, payload: Mp4Form, db: DbSession, current_user: CanEdit) -> dict[str, Any]:
    obj = await _get(db, Video, item_id, "MP4", source="upload")
    obj.title = payload.title
    if payload.date:
        obj.upload_date = payload.date
    for field, value in (("duration", payload.duration), ("file_size", payload.size),
                         ("video_file_url", payload.file_url), ("thumbnail_url", payload.thumbnail)):
        if value is not None:
            setattr(obj, field, value)
    apply_te(obj, te_updates(payload, MEDIA_TE))
    await _log(db, current_user, "mp4_updated", f"Updated MP4 {obj.title}", obj.id)
    await db.commit()
    return mp4_row(await _get(db, Video, item_id, "MP4"))


@router.delete("/mp4/{item_id}", summary="Delete an MP4 download")
async def delete_mp4(item_id: str, db: DbSession, current_user: CanDelete) -> dict[str, Any]:
    obj = await _get(db, Video, item_id, "MP4", source="upload")
    await _log(db, current_user, "mp4_deleted", f"Deleted MP4 {obj.title}", obj.id)
    await db.delete(obj)
    await db.commit()
    return {"success": True}
