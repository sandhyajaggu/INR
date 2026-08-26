"""Generic media upload endpoint.

Decoupled from resource CRUD: the frontend uploads a file here first, gets
back a URL, then sends that URL as a plain string field in the module's own
create/update JSON body. Keeps every other router's request bodies pure JSON
(no multipart), and keeps all disk access behind the FileStorage interface.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, UploadFile

from app.core.dependencies import require_staff
from app.core.storage import FileStorage, get_file_storage

router = APIRouter(prefix="/files", tags=["Files"])

UploadSubfolder = Literal[
    "voters", "beneficiaries", "gallery", "mp3", "videos", "press", "events", "surveys",
    "local_leaders", "janata_darbar", "achievements",
]


@router.post(
    "/upload",
    summary="Upload a media file",
    description="Stores the file (local disk for now, swappable for S3 later) and returns its public URL.",
    dependencies=[Depends(require_staff)],
)
async def upload_file(
    file: UploadFile,
    subfolder: UploadSubfolder,
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> dict[str, str]:
    url = await storage.save(file, subfolder)
    return {"url": url}
