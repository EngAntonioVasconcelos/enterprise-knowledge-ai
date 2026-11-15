"""Object storage for originals and normalized snapshots (ADR-004).

Business code uses this interface only; the backend is configuration.
Development and tests use a local folder; production gets an
S3-compatible backend with hosting (Phase 10).

Keys are built from ids and hashes, never from titles or file names, so a
key reveals nothing about a document. Writes are content-addressed and
idempotent: writing the same bytes to the same key again is harmless,
which makes retries safe.
"""

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import settings


_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*$")


class StorageKeyError(ValueError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


def check_key(key: str) -> str:
    if len(key) > 500 or not _KEY.match(key) or ".." in key:
        raise StorageKeyError(f"Invalid storage key: {key!r}")
    return key


class LocalObjectStorage:
    """A folder on disk; for development and tests only."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        if self.root not in path.parents:
            raise StorageKeyError(f"Key escapes the storage root: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temporary file, then rename: a reader never sees half
        # a file, and a crash leaves no partial object under the key.
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(data)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

        return StoredObject(
            key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def get_object_storage() -> ObjectStorage:
    if settings.STORAGE_BACKEND == "local":
        return LocalObjectStorage(settings.LOCAL_STORAGE_PATH)
    raise ValueError(f"Unknown storage backend: {settings.STORAGE_BACKEND}")
