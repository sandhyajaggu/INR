"""File storage abstraction.

Route/service code depends only on `FileStorage`, never on the filesystem
directly, so the local-disk implementation below can be swapped for an
S3-compatible backend later without touching any route.
"""

import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


class FileStorage(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, subfolder: str) -> str:
        """Persist the upload and return a public URL/path for it."""

    @abstractmethod
    def delete(self, url: str) -> None:
        """Best-effort delete of a previously saved file."""

    @abstractmethod
    async def replace(self, url: str, file: UploadFile) -> None:
        """Overwrite the content of a previously saved file, keeping its URL."""


class LocalDiskStorage(FileStorage):
    def __init__(self, base_dir: str = settings.upload_dir, base_url: str = settings.upload_base_url):
        self.base_dir = Path(base_dir)
        self.base_url = base_url.rstrip("/")

    async def save(self, file: UploadFile, subfolder: str) -> str:
        target_dir = self.base_dir / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(file.filename or "").suffix
        filename = f"{uuid.uuid4().hex}{suffix}"
        target_path = target_dir / filename

        contents = await file.read()
        target_path.write_bytes(contents)
        await file.seek(0)

        return f"{self.base_url}/{subfolder}/{filename}"

    def _path_for(self, url: str) -> Path:
        relative = url.removeprefix(self.base_url).lstrip("/")
        path = (self.base_dir / relative).resolve()
        if not path.is_relative_to(self.base_dir.resolve()):
            raise ValueError("File URL is outside the upload directory")
        return path

    def delete(self, url: str) -> None:
        path = self._path_for(url)
        if path.exists():
            path.unlink(missing_ok=True)

    async def replace(self, url: str, file: UploadFile) -> None:
        path = self._path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(await file.read())
        await file.seek(0)


def get_file_storage() -> FileStorage:
    if settings.storage_backend == "local":
        return LocalDiskStorage()
    raise NotImplementedError(f"Storage backend '{settings.storage_backend}' is not implemented")
