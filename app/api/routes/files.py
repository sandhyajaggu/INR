"""Uploaded files.

The frontend uploads a file here first, gets back a URL, then sends that URL
as a plain string field in the module's own create/update JSON body. Every
upload is also recorded in `uploaded_files` so it can be listed, replaced and
deleted.

    POST   /files/upload?subfolder=gallery   upload (multipart "file")        -> {url, id, ...}
    GET    /files?subfolder=&q=&page=        list uploads (newest first)
    GET    /files/{id}                       one upload
    PUT    /files/{id}                       replace content (multipart "file") and/or rename
    DELETE /files/{id}                       delete from storage and the list

Replacing with the same file type keeps the URL, so records that store it keep
working. A different file type gets a new URL ("url_changed": true).
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.dependencies import CurrentUser, DbSession, RequireStaff
from app.core.ids import format_id, parse_id
from app.core.storage import FileStorage, get_file_storage
from app.models.notifications import UploadedFile
from app.models.staff import StaffUser

router = APIRouter(prefix="/files", tags=["Files"])

UploadSubfolder = Literal[
    "voters", "beneficiaries", "gallery", "mp3", "videos", "press", "events", "surveys",
    "local_leaders", "janata_darbar", "achievements",
]
Storage = Annotated[FileStorage, Depends(get_file_storage)]
PREFIX = "FILE"


def _check_size(file: UploadFile) -> None:
    limit = settings.max_upload_size_mb * 1024 * 1024
    if file.size is not None and file.size > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File is larger than {settings.max_upload_size_mb} MB"
        )


async def _row(db, f: UploadedFile) -> dict[str, Any]:
    uploader = await db.get(StaffUser, f.uploaded_by) if f.uploaded_by else None
    return {
        "id": format_id(PREFIX, f.id),
        "url": f.url,
        "subfolder": f.subfolder,
        "name": f.original_name,
        "content_type": f.content_type,
        "size": f.size_bytes,
        "uploaded_by": uploader.name if uploader else None,
        "created_at": f.created_at,
        "updated_at": f.updated_at,
    }


async def _get(db, file_id: str) -> UploadedFile:
    obj = await db.get(UploadedFile, parse_id(file_id, label="File"))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return obj


@router.post(
    "/upload",
    summary="Upload a media file",
    description="Stores the file (local disk for now, swappable for S3 later) and returns its public URL.",
)
async def upload_file(
    file: UploadFile, subfolder: UploadSubfolder, storage: Storage, db: DbSession, current_user: RequireStaff
) -> dict[str, Any]:
    _check_size(file)
    url = await storage.save(file, subfolder)
    obj = UploadedFile(
        url=url,
        subfolder=subfolder,
        original_name=(file.filename or None),
        content_type=file.content_type,
        size_bytes=file.size,
        uploaded_by=current_user.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return await _row(db, obj)


@router.get("", summary="List uploaded files (newest first)")
async def list_files(
    db: DbSession,
    current_user: CurrentUser,
    subfolder: UploadSubfolder | None = Query(None),
    q: str | None = Query(None, description="Search by file name"),
    content_type: str | None = Query(None, description="Prefix match, e.g. image/ or audio/"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    conds = []
    if subfolder:
        conds.append(UploadedFile.subfolder == subfolder)
    if q and q.strip():
        term = f"%{q.strip()}%"
        conds.append(or_(UploadedFile.original_name.ilike(term), UploadedFile.url.ilike(term)))
    if content_type:
        conds.append(UploadedFile.content_type.ilike(f"{content_type}%"))
    total = (await db.execute(select(func.count()).select_from(UploadedFile).where(*conds))).scalar_one()
    rows = (
        await db.execute(
            select(UploadedFile).where(*conds)
            .order_by(UploadedFile.created_at.desc(), UploadedFile.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [await _row(db, f) for f in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/{file_id}", summary="One uploaded file")
async def get_file(file_id: str, db: DbSession, current_user: CurrentUser) -> dict[str, Any]:
    return await _row(db, await _get(db, file_id))


@router.put("/{file_id}", summary="Replace a file's content and/or rename it")
async def update_file(
    file_id: str,
    storage: Storage,
    db: DbSession,
    current_user: RequireStaff,
    file: UploadFile | None = None,
    name: str | None = Form(None, max_length=255),
) -> dict[str, Any]:
    obj = await _get(db, file_id)
    if file is None and name is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Send a new 'file', a new 'name', or both")
    url_changed = False
    old_url = None
    if file is not None:
        _check_size(file)
        if Path(file.filename or "").suffix.lower() == Path(obj.url).suffix.lower():
            await storage.replace(obj.url, file)
        else:
            old_url = obj.url
            obj.url = await storage.save(file, obj.subfolder)
            url_changed = True
        obj.content_type = file.content_type
        obj.size_bytes = file.size
        if name is None:
            obj.original_name = file.filename or obj.original_name
    if name is not None:
        obj.original_name = name.strip() or obj.original_name
    await db.commit()
    if old_url:
        storage.delete(old_url)
    await db.refresh(obj)
    return {**await _row(db, obj), "url_changed": url_changed}


@router.delete("/{file_id}", summary="Delete an uploaded file")
async def delete_file(file_id: str, storage: Storage, db: DbSession, current_user: RequireStaff) -> dict[str, bool]:
    obj = await _get(db, file_id)
    url = obj.url
    await db.delete(obj)
    await db.commit()
    storage.delete(url)
    return {"success": True}
