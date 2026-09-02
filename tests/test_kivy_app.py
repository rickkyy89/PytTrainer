"""Kivy-home behavior tests; these modules never import Kivy."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.drive_sync import RemoteScheda
from kivy_app.config import AppConfigError, DEFAULT_FOLDER_ID, FolderConfigStore
from kivy_app.controller import DriveHomeController, HomeUnavailableError


class FakeProvider:
    def __init__(self, error=None):
        self.error = error
        self.scopes = None

    def get_credentials(self, scopes):
        self.scopes = scopes
        if self.error:
            raise self.error
        return "credentials"


class FakeSync:
    def __init__(self, service, folder_id, cache_dir):
        self.service = service
        self.folder_id = folder_id
        self.cache_dir = Path(cache_dir)
        self.records = [RemoteScheda("gambe.scheda", "one", "2026-09-02T10:00:00Z")]
        self.downloaded = None
        self.created = []
        self.deleted = []
        self.error = None

    def list_schede(self):
        if self.error:
            raise self.error
        return self.records

    def download_scheda(self, file_id, name):
        if self.error:
            raise self.error
        self.downloaded = (file_id, name)
        return self.cache_dir / name

    def create_scheda(self, path):
        if self.error:
            raise self.error
        self.created.append(Path(path))
        return SimpleNamespace(remote=RemoteScheda(Path(path).name, "new", "2026-09-02T11:00:00Z"))

    def delete_scheda(self, file_id):
        if self.error:
            raise self.error
        self.deleted.append(file_id)


def make_controller(tmp_path, *, provider=None, loader=None, saver=None):
    instances = []

    def sync_factory(service, folder_id, cache_dir):
        sync = FakeSync(service, folder_id, cache_dir)
        instances.append(sync)
        return sync

    controller = DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=provider or FakeProvider(),
        drive_service_factory=lambda credentials: f"drive:{credentials}",
        sync_factory=sync_factory,
        load_scheda=loader or (lambda path: ([{
            "nome": "Squat", "spiegazione": "Scendi controllando.", "note": "Ginocchia in linea.",
            "ripetizioni": "3x12", "recupero": "90 SEC", "gruppo": "Gambe",
            "frame_start": "start.jpg", "frame_finish": "finish.jpg",
        }], f"{path}.work")),
        save_scheda=saver or (lambda exercises, path, titolo: Path(path).write_bytes(b"bundle")),
    )
    return controller, instances


def test_folder_configuration_defaults_then_persists_added_and_selected_folder(tmp_path):
    store = FolderConfigStore(tmp_path / "folders.json")

    assert store.load().current_folder_id == DEFAULT_FOLDER_ID
    controller, _ = make_controller(tmp_path)
    added = controller.add_folder(" second-folder ")
    selected = controller.select_folder(DEFAULT_FOLDER_ID)

    assert added.folder_ids == (DEFAULT_FOLDER_ID, "second-folder")
    assert selected.current_folder_id == DEFAULT_FOLDER_ID
    assert FolderConfigStore(tmp_path / "folders.json").load() == selected


def test_invalid_folder_configuration_and_unknown_selection_are_rejected(tmp_path):
    store = FolderConfigStore(tmp_path / "folders.json")
    store.path.write_text('{"folder_ids": [], "current_folder_id": ""}', encoding="utf-8")
    with pytest.raises(AppConfigError):
        store.load()

    controller, _ = make_controller(tmp_path / "valid")
    with pytest.raises(AppConfigError):
        controller.select_folder("not-configured")


def test_refresh_composes_drive_lazily_with_provider_and_current_folder(tmp_path):
    provider = FakeProvider()
    controller, instances = make_controller(tmp_path, provider=provider)

    records = controller.refresh()

    assert [record.name for record in records] == ["gambe.scheda"]
    assert provider.scopes == ["https://www.googleapis.com/auth/drive"]
    assert instances[0].service == "drive:credentials"
    assert instances[0].folder_id == DEFAULT_FOLDER_ID


def test_open_downloads_and_exposes_readonly_exercise_and_frame_model(tmp_path):
    controller, instances = make_controller(tmp_path)
    remote = controller.refresh()[0]

    scheda = controller.open(remote)

    assert instances[0].downloaded == ("one", "gambe.scheda")
    assert scheda.name == "gambe.scheda"
    assert scheda.exercises[0].name == "Squat"
    assert scheda.exercises[0].frame_start == "start.jpg"


def test_create_writes_empty_bundle_and_uploads_it(tmp_path):
    saved = []
    controller, instances = make_controller(
        tmp_path, saver=lambda exercises, path, titolo: (saved.append((exercises, Path(path), titolo)), Path(path).write_bytes(b"zip")),
    )

    remote = controller.create("Nuova scheda")

    assert saved == [([], tmp_path / "cache" / "Nuova scheda.scheda", "Nuova scheda")]
    assert instances[0].created == [tmp_path / "cache" / "Nuova scheda.scheda"]
    assert remote.id == "new"


def test_delete_delegates_to_drive(tmp_path):
    controller, instances = make_controller(tmp_path)
    remote = controller.refresh()[0]

    controller.delete(remote)

    assert instances[0].deleted == ["one"]


@pytest.mark.parametrize("operation", ["refresh", "open", "create", "delete"])
def test_drive_errors_are_mapped_to_explicit_unavailable_state(tmp_path, operation):
    controller, instances = make_controller(tmp_path)
    remote = controller.refresh()[0]
    instances[0].error = OSError("offline")

    with pytest.raises(HomeUnavailableError, match="Drive non disponibile"):
        if operation == "refresh":
            controller.refresh()
        elif operation == "open":
            controller.open(remote)
        elif operation == "create":
            controller.create("nuova")
        else:
            controller.delete(remote)


def test_authentication_errors_are_mapped_to_explicit_unavailable_state(tmp_path):
    controller, _ = make_controller(tmp_path, provider=FakeProvider(OSError("offline")))

    with pytest.raises(HomeUnavailableError, match="Drive non disponibile"):
        controller.refresh()
