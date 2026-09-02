"""Synchronize ``.scheda`` bundles with one configured Google Drive folder.

``DriveSync`` deliberately accepts a ready-to-use Google Drive service rather
than creating credentials or performing network setup.  Its small facade uses
the usual Google API request style::

    service.files().list(...).execute()
    service.files().get(...).execute()
    service.files().get_media(...).execute()
    service.files().create(...).execute()
    service.files().update(...).execute()
    service.files().delete(...).execute()

The cache contains ``.drive-sync-state.json``.  It records the remote file ID,
the remote modified timestamp at the last successful sync, plus a SHA-256
fingerprint and mtime for the local bundle then observed.  Consumers must
handle a returned ``SyncConflict`` explicitly; this module never selects either
version automatically.
"""

from __future__ import annotations

import json
import os
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.http import MediaFileUpload


STATE_FILENAME = ".drive-sync-state.json"
MIME_TYPE_SCHEDA = "application/zip"


class DriveSyncError(Exception):
    """Raised when a local path or Drive response cannot be synchronized."""


@dataclass(frozen=True)
class RemoteScheda:
    """The Drive metadata needed to identify a remote workout bundle."""

    name: str
    id: str
    modified_time: str


@dataclass(frozen=True)
class SyncConflict:
    """A local edit and a newer remote edit need a UI policy decision."""

    file_id: str
    name: str
    local_modified_time: str
    remote_modified_time: str
    last_sync_remote_modified_time: str


@dataclass(frozen=True)
class UploadResult:
    """Metadata for a successfully created or updated remote bundle."""

    remote: RemoteScheda
    created: bool


class DriveSync:
    """Drive facade for ``.scheda`` files in one explicitly configured folder."""

    def __init__(self, drive_service, folder_id: str, cache_dir: str | os.PathLike, *, media_factory=None):
        if not folder_id:
            raise ValueError("folder_id is required.")
        self._drive_service = drive_service
        self.folder_id = folder_id
        self.cache_dir = Path(cache_dir).resolve()
        self._media_factory = media_factory or self._default_media_factory

    @staticmethod
    def _default_media_factory(path: str):
        return MediaFileUpload(path, mimetype=MIME_TYPE_SCHEDA, resumable=False)

    def list_schede(self) -> list[RemoteScheda]:
        """List bundles in the configured folder, sorted case-insensitively by name."""
        schede = []
        page_token = None
        while True:
            request = {
                "q": f"'{self.folder_id}' in parents and trashed = false",
                "fields": "files(id,name,modifiedTime),nextPageToken",
            }
            if page_token:
                request["pageToken"] = page_token
            response = self._drive_service.files().list(**request).execute()
            schede.extend(
                self._remote(file) for file in response.get("files", [])
                if file.get("name", "").endswith(".scheda")
            )
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return sorted(schede, key=lambda scheda: (scheda.name.casefold(), scheda.id))

    def download_scheda(self, file_id: str, name: str | None = None) -> Path:
        """Download a bundle into the cache and record its last-sync timestamp."""
        metadata = self._remote(self._drive_service.files().get(
            fileId=file_id, fields="id,name,modifiedTime"
        ).execute())
        if name is not None and name != metadata.name:
            raise DriveSyncError("The supplied name does not match the remote file.")
        destination = self._cache_path(metadata.name)
        content = self._drive_service.files().get_media(fileId=file_id).execute()
        if not isinstance(content, bytes):
            raise DriveSyncError("Drive media download did not return bytes.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        state = self._load_state()
        state[str(destination)] = {
            "file_id": metadata.id,
            "name": metadata.name,
            "remote_modified_time": metadata.modified_time,
            "local_mtime_ns": destination.stat().st_mtime_ns,
            "local_fingerprint": self._fingerprint(destination),
        }
        self._save_state(state)
        return destination

    def upload_scheda(self, local_path: str | os.PathLike, file_id: str | None = None) -> UploadResult | SyncConflict:
        """Create or update a bundle, returning a conflict instead of overwriting one."""
        path = self._validate_local_path(local_path)
        state = self._load_state()
        entry = state.get(str(path))
        remote_id = file_id or (entry or {}).get("file_id")
        if remote_id is None:
            return self.create_scheda(path)

        remote = self._remote(self._drive_service.files().get(
            fileId=remote_id, fields="id,name,modifiedTime"
        ).execute())
        if entry and self._has_conflict(path, entry, remote):
            return SyncConflict(
                file_id=remote.id,
                name=remote.name,
                local_modified_time=self._format_local_time(path.stat().st_mtime_ns),
                remote_modified_time=remote.modified_time,
                last_sync_remote_modified_time=entry["remote_modified_time"],
            )

        response = self._drive_service.files().update(
            fileId=remote_id,
            body={"name": path.name},
            media_body=self._media_factory(str(path)),
            fields="id,name,modifiedTime",
        ).execute()
        uploaded = self._remote(response)
        self._record_sync(path, uploaded)
        return UploadResult(uploaded, created=False)

    def create_scheda(self, local_path: str | os.PathLike) -> UploadResult:
        """Create a new bundle in the configured folder."""
        path = self._validate_local_path(local_path)
        response = self._drive_service.files().create(
            body={"name": path.name, "parents": [self.folder_id]},
            media_body=self._media_factory(str(path)),
            fields="id,name,modifiedTime",
        ).execute()
        remote = self._remote(response)
        self._record_sync(path, remote)
        return UploadResult(remote, created=True)

    def delete_scheda(self, file_id: str) -> None:
        """Delete a remote bundle and remove all matching cache sync records."""
        self._drive_service.files().delete(fileId=file_id).execute()
        state = self._load_state()
        retained = {path: entry for path, entry in state.items() if entry.get("file_id") != file_id}
        if retained != state:
            self._save_state(retained)

    def _record_sync(self, path: Path, remote: RemoteScheda) -> None:
        state = self._load_state()
        state[str(path)] = {
            "file_id": remote.id,
            "name": remote.name,
            "remote_modified_time": remote.modified_time,
            "local_mtime_ns": path.stat().st_mtime_ns,
            "local_fingerprint": self._fingerprint(path),
        }
        self._save_state(state)

    def _has_conflict(self, path: Path, entry: dict, remote: RemoteScheda) -> bool:
        fingerprint = entry.get("local_fingerprint")
        if isinstance(fingerprint, str):
            local_changed = self._fingerprint(path) != fingerprint
        else:
            # Legacy records have no content baseline.  A changed mtime is the
            # only evidence of a local edit, so preserve the old conflict-safe
            # behavior rather than overwriting a newer remote copy.
            local_changed = path.stat().st_mtime_ns != entry.get("local_mtime_ns")
        return local_changed and self._timestamp(remote.modified_time) > self._timestamp(entry["remote_modified_time"])

    @staticmethod
    def _fingerprint(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as bundle:
            for chunk in iter(lambda: bundle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _cache_path(self, name: str) -> Path:
        if not name.endswith(".scheda") or Path(name).name != name:
            raise DriveSyncError("Remote file name is not a safe .scheda filename.")
        return self.cache_dir / name

    @staticmethod
    def _validate_local_path(local_path: str | os.PathLike) -> Path:
        path = Path(local_path).resolve()
        if not path.is_file() or path.suffix != ".scheda":
            raise DriveSyncError("local_path must be an existing .scheda file.")
        return path

    def _load_state(self) -> dict:
        try:
            with (self.cache_dir / STATE_FILENAME).open(encoding="utf-8") as state_file:
                state = json.load(state_file)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise DriveSyncError("Could not read Drive sync state.") from exc
        if not isinstance(state, dict):
            raise DriveSyncError("Drive sync state must be a JSON object.")
        return state

    def _save_state(self, state: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.cache_dir / STATE_FILENAME
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, target)

    @staticmethod
    def _remote(metadata: dict) -> RemoteScheda:
        try:
            return RemoteScheda(metadata["name"], metadata["id"], metadata["modifiedTime"])
        except KeyError as exc:
            raise DriveSyncError(f"Drive metadata lacks {exc.args[0]!r}.") from exc

    @staticmethod
    def _timestamp(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise DriveSyncError(f"Invalid Drive modifiedTime: {value!r}.") from exc

    @staticmethod
    def _format_local_time(mtime_ns: int) -> str:
        return datetime.fromtimestamp(mtime_ns / 1_000_000_000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
