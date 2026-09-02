"""Drive sync tests using an in-memory fake that mirrors files() requests."""

import json
import os
import sys
from hashlib import sha256
from pathlib import Path

RADICE_PROGETTO = Path(__file__).resolve().parent.parent
if str(RADICE_PROGETTO) not in sys.path:
    sys.path.insert(0, str(RADICE_PROGETTO))

from core.drive_sync import DriveSync, SyncConflict, UploadResult  # noqa: E402


class FakeRequest:
    def __init__(self, callback):
        self._callback = callback

    def execute(self):
        return self._callback()


class FakeMedia:
    def __init__(self, filename):
        self.filename = filename


class FakeFiles:
    def __init__(self, folder_id):
        self.folder_id = folder_id
        self.records = {}
        self.calls = []
        self.list_page_size = None
        self._next_id = 1

    def add(self, name, content, modified_time, file_id=None, parents=None):
        file_id = file_id or f"file-{self._next_id}"
        self._next_id += 1
        self.records[file_id] = {"id": file_id, "name": name, "content": content,
                                 "modifiedTime": modified_time, "parents": parents or [self.folder_id]}
        return file_id

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        records = [record for record in self.records.values() if self.folder_id in record["parents"]]
        if self.list_page_size is None:
            return FakeRequest(lambda: {"files": [self._metadata(record) for record in records]})
        start = int(kwargs.get("pageToken", 0))
        page = records[start:start + self.list_page_size]
        response = {"files": [self._metadata(record) for record in page]}
        if start + self.list_page_size < len(records):
            response["nextPageToken"] = str(start + self.list_page_size)
        return FakeRequest(lambda: response)

    def get(self, fileId, **kwargs):
        self.calls.append(("get", fileId, kwargs))
        return FakeRequest(lambda: self._metadata(self.records[fileId]))

    def get_media(self, fileId):
        self.calls.append(("get_media", fileId))
        return FakeRequest(lambda: self.records[fileId]["content"])

    def create(self, body, media_body, **kwargs):
        self.calls.append(("create", body, kwargs))
        def create():
            return self._metadata(self.records[self.add(body["name"], Path(media_body.filename).read_bytes(),
                                                        "2026-09-02T12:00:00Z", parents=body["parents"])])
        return FakeRequest(create)

    def update(self, fileId, body, media_body, **kwargs):
        self.calls.append(("update", fileId, body, kwargs))
        def update():
            record = self.records[fileId]
            record["name"] = body["name"]
            record["content"] = Path(media_body.filename).read_bytes()
            record["modifiedTime"] = "2026-09-02T13:00:00Z"
            return self._metadata(record)
        return FakeRequest(update)

    def delete(self, fileId):
        self.calls.append(("delete", fileId))
        return FakeRequest(lambda: self.records.pop(fileId))

    @staticmethod
    def _metadata(record):
        return {key: record[key] for key in ("id", "name", "modifiedTime")}


class FakeDriveClient:
    def __init__(self, folder_id="configured-folder"):
        self.files_api = FakeFiles(folder_id)

    def files(self):
        return self.files_api


def sync(tmp_path):
    client = FakeDriveClient()
    return DriveSync(client, "configured-folder", tmp_path / "cache", media_factory=FakeMedia), client


def test_lists_only_folder_schede_with_sorted_metadata(tmp_path):
    service, client = sync(tmp_path)
    client.files_api.add("zeta.scheda", b"z", "2026-09-02T10:00:00Z")
    client.files_api.add("Alpha.scheda", b"a", "2026-09-02T11:00:00Z")
    client.files_api.add("readme.txt", b"x", "2026-09-02T12:00:00Z")
    client.files_api.add("outside.scheda", b"x", "2026-09-02T12:00:00Z", parents=["other-folder"])

    listed = service.list_schede()

    assert [(item.name, item.id, item.modified_time) for item in listed] == [
        ("Alpha.scheda", "file-2", "2026-09-02T11:00:00Z"),
        ("zeta.scheda", "file-1", "2026-09-02T10:00:00Z"),
    ]
    assert "configured-folder" in client.files_api.calls[0][1]["q"]


def test_lists_schede_from_all_drive_pages(tmp_path):
    service, client = sync(tmp_path)
    client.files_api.list_page_size = 1
    client.files_api.add("zeta.scheda", b"z", "2026-09-02T10:00:00Z")
    client.files_api.add("readme.txt", b"x", "2026-09-02T11:00:00Z")
    client.files_api.add("Alpha.scheda", b"a", "2026-09-02T12:00:00Z")

    listed = service.list_schede()

    assert [item.name for item in listed] == ["Alpha.scheda", "zeta.scheda"]
    list_calls = [call for call in client.files_api.calls if call[0] == "list"]
    assert [call[1].get("pageToken") for call in list_calls] == [None, "1", "2"]


def test_download_caches_bundle_and_records_last_remote_sync(tmp_path):
    service, client = sync(tmp_path)
    file_id = client.files_api.add("gambe.scheda", b"bundle", "2026-09-02T10:00:00Z")

    local = service.download_scheda(file_id)

    assert local.read_bytes() == b"bundle"
    state = json.loads((tmp_path / "cache" / ".drive-sync-state.json").read_text())
    assert state[str(local)]["file_id"] == file_id
    assert state[str(local)]["remote_modified_time"] == "2026-09-02T10:00:00Z"
    assert state[str(local)]["local_mtime_ns"] == local.stat().st_mtime_ns
    assert state[str(local)]["local_fingerprint"] == sha256(b"bundle").hexdigest()


def test_upload_creates_then_updates_known_local_bundle(tmp_path):
    service, client = sync(tmp_path)
    local = tmp_path / "nuova.scheda"
    local.write_bytes(b"first")

    created = service.upload_scheda(local)
    assert isinstance(created, UploadResult) and created.created
    assert client.files_api.records[created.remote.id]["parents"] == ["configured-folder"]
    assert client.files_api.records[created.remote.id]["content"] == b"first"

    local.write_bytes(b"second")
    os.utime(local, ns=(local.stat().st_atime_ns, local.stat().st_mtime_ns + 1))
    updated = service.upload_scheda(local)
    assert isinstance(updated, UploadResult) and not updated.created
    assert updated.remote.id == created.remote.id
    assert client.files_api.records[created.remote.id]["content"] == b"second"


def test_upload_reports_conflict_for_content_edit_with_unchanged_mtime(tmp_path):
    service, client = sync(tmp_path)
    file_id = client.files_api.add("gambe.scheda", b"original", "2026-09-02T10:00:00Z")
    local = service.download_scheda(file_id)
    original_mtime = local.stat().st_mtime_ns
    local.write_bytes(b"local edit")
    os.utime(local, ns=(local.stat().st_atime_ns, original_mtime))
    client.files_api.records[file_id]["modifiedTime"] = "2026-09-02T11:00:00Z"

    conflict = service.upload_scheda(local)
    assert isinstance(conflict, SyncConflict)
    assert conflict.local_modified_time.endswith("Z")
    assert conflict.remote_modified_time == "2026-09-02T11:00:00Z"
    assert conflict.last_sync_remote_modified_time == "2026-09-02T10:00:00Z"
    assert client.files_api.records[file_id]["content"] == b"original"

    local = service.download_scheda(file_id)
    local.write_bytes(b"another local edit")
    os.utime(local, ns=(local.stat().st_atime_ns, local.stat().st_mtime_ns + 1))
    result = service.upload_scheda(local)
    assert isinstance(result, UploadResult)
    assert client.files_api.records[file_id]["content"] == b"another local edit"


def test_upload_legacy_state_uses_mtime_to_protect_newer_remote(tmp_path):
    service, client = sync(tmp_path)
    file_id = client.files_api.add("gambe.scheda", b"original", "2026-09-02T10:00:00Z")
    local = service.download_scheda(file_id)
    state_path = tmp_path / "cache" / ".drive-sync-state.json"
    state = json.loads(state_path.read_text())
    del state[str(local)]["local_fingerprint"]
    state_path.write_text(json.dumps(state))

    local.write_bytes(b"local edit")
    os.utime(local, ns=(local.stat().st_atime_ns, local.stat().st_mtime_ns + 1))
    client.files_api.records[file_id]["modifiedTime"] = "2026-09-02T11:00:00Z"

    conflict = service.upload_scheda(local)

    assert isinstance(conflict, SyncConflict)
    assert client.files_api.records[file_id]["content"] == b"original"


def test_delete_removes_remote_file_and_cached_sync_record(tmp_path):
    service, client = sync(tmp_path)
    file_id = client.files_api.add("gambe.scheda", b"bundle", "2026-09-02T10:00:00Z")
    service.download_scheda(file_id)

    service.delete_scheda(file_id)

    assert file_id not in client.files_api.records
    state = json.loads((tmp_path / "cache" / ".drive-sync-state.json").read_text())
    assert state == {}
