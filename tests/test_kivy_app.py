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
from kivy_app.main import build_controller, duplicate_default_name


class FakeProvider:
    def __init__(self, error=None):
        self.error = error
        self.scopes = None

    def get_credentials(self, scopes):
        self.scopes = scopes
        if self.error:
            raise self.error
        return "credentials"


class FakeAndroidBridge:
    def __init__(self):
        self.authorization_started = 0

    def start_authorization(self):
        self.authorization_started += 1

    def get_access_token(self):
        return "native-access-token"

    def get_status(self):
        return "authorized"


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
        self.ahead = False

    def list_schede(self):
        if self.error:
            raise self.error
        return self.records

    def list_remote(self, suffix):
        if self.error:
            raise self.error
        return [record for record in self.records if record.name.casefold().endswith(suffix.casefold())]

    def download_scheda(self, file_id, name):
        if self.error:
            raise self.error
        self.downloaded = (file_id, name)
        return self.cache_dir / name

    def download_file(self, file_id, name):
        if self.error:
            raise self.error
        self.downloaded = (file_id, name)
        return self.cache_dir / name

    def local_ahead(self, local_path, file_id=None):
        return self.ahead

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


def test_android_composition_starts_native_authorization_at_launch(tmp_path):
    bridge = FakeAndroidBridge()

    controller = build_controller(
        tmp_path, is_android=True, android_bridge_factory=lambda: bridge,
    )

    assert isinstance(controller, DriveHomeController)
    assert bridge.authorization_started == 1


def test_pc_composition_never_constructs_or_starts_android_authorization(tmp_path):
    bridge_factory_called = False

    def bridge_factory():
        nonlocal bridge_factory_called
        bridge_factory_called = True
        return FakeAndroidBridge()

    controller = build_controller(
        tmp_path, is_android=False, android_bridge_factory=bridge_factory,
    )

    assert isinstance(controller, DriveHomeController)
    assert bridge_factory_called is False


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


def test_duplicate_downloads_source_and_creates_bundle_with_requested_name(tmp_path):
    controller, instances = make_controller(tmp_path)
    remote = controller.refresh()[0]
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "gambe.scheda").write_bytes(b"bundle")

    created = controller.duplicate(remote, "gambe copia")

    assert instances[0].downloaded == ("one", "gambe.scheda")
    assert instances[0].created == [cache / "gambe copia.scheda"]
    assert (cache / "gambe copia.scheda").read_bytes() == b"bundle"
    assert created.name == "gambe copia.scheda"


def test_duplicate_avoids_names_already_taken_locally_and_remotely(tmp_path):
    controller, instances = make_controller(tmp_path)
    remote = controller.refresh()[0]
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "gambe.scheda").write_bytes(b"bundle")
    instances[0].records = [remote,
                            RemoteScheda("Copia.scheda", "r1", "2026-09-02T10:00:00Z"),
                            RemoteScheda("Copia (2).scheda", "r2", "2026-09-02T10:00:00Z")]
    (cache / "Copia (3).scheda").write_bytes(b"stale")

    created = controller.duplicate(remote, "Copia")

    # .scheda aggiunto, "(2)" remoto occupato, "(3)" locale occupato → "(4)".
    assert created.name == "Copia (4).scheda"
    assert instances[0].created == [cache / "Copia (4).scheda"]
    assert (cache / "Copia (3).scheda").read_bytes() == b"stale"


def test_duplicate_keeps_unsynced_local_copy_and_skips_download(tmp_path):
    controller, instances = make_controller(tmp_path)
    remote = controller.refresh()[0]
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "gambe.scheda").write_bytes(b"local edits")
    instances[0].ahead = True

    created = controller.duplicate(remote, "gambe copia")

    assert instances[0].downloaded is None
    assert created.name == "gambe copia.scheda"
    assert (cache / "gambe copia.scheda").read_bytes() == b"local edits"
    assert controller.avvertenza and "duplicata da locale" in controller.avvertenza


def test_duplicate_default_name_suggerisce_copia_senza_estensione():
    assert duplicate_default_name("gambe.scheda") == "gambe (copia)"
    assert duplicate_default_name("Gambe Day") == "Gambe Day (copia)"


def test_list_csv_e_download_csv_delegano_a_drive(tmp_path):
    controller, instances = make_controller(tmp_path)
    remote = controller.refresh()[0]
    instances[0].records = [remote,
                            RemoteScheda("esercizi.csv", "csv1", "2026-09-02T11:00:00Z")]

    csvs = controller.list_csv()
    percorso = controller.download_csv(csvs[0])

    assert [remote.name for remote in csvs] == ["esercizi.csv"]
    assert instances[0].downloaded == ("csv1", "esercizi.csv")
    assert percorso == tmp_path / "cache" / "esercizi.csv"


@pytest.mark.parametrize("operation", ["refresh", "open", "create", "delete", "duplicate", "list_csv", "download_csv"])
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
        elif operation == "duplicate":
            controller.duplicate(remote, "copia")
        elif operation == "list_csv":
            controller.list_csv()
        elif operation == "download_csv":
            controller.download_csv(RemoteScheda("esercizi.csv", "csv1", "2026-09-02T10:00:00Z"))
        else:
            controller.delete(remote)


def test_authentication_errors_are_mapped_to_explicit_unavailable_state(tmp_path):
    controller, _ = make_controller(tmp_path, provider=FakeProvider(OSError("offline")))

    with pytest.raises(HomeUnavailableError, match="Drive non disponibile"):
        controller.refresh()


def test_expired_native_token_triggers_riautentica_and_one_retry(tmp_path):
    from core.platform import CredentialProviderError

    class ReauthProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.riautenticazioni = 0

        def riautentica(self):
            self.riautenticazioni += 1
            return True

    provider = ReauthProvider()
    casi = {"chiamate": 0}

    def sync_factory(service, folder_id, cache_dir):
        class FlakySync:
            def list_schede(self):
                casi["chiamate"] += 1
                if casi["chiamate"] == 1:
                    raise CredentialProviderError("Autorizzazione Google Android non disponibile.")
                return [RemoteScheda("gambe.scheda", "one", "2026-09-02T10:00:00Z")]

        return FlakySync()

    controller = DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=provider,
        drive_service_factory=lambda credentials: "service",
        sync_factory=sync_factory,
    )

    records = controller.refresh()

    assert provider.riautenticazioni == 1
    assert [r.id for r in records] == ["one"]


def test_riautentica_assente_o_fallita_lascia_errore_chiara(tmp_path):
    from core.platform import CredentialProviderError

    class DeadReauthProvider(FakeProvider):
        def riautentica(self):
            return False

    def sync_factory(service, folder_id, cache_dir):
        class AlwaysAuthFail:
            def list_schede(self):
                raise CredentialProviderError("Autorizzazione Google Android non disponibile.")

        return AlwaysAuthFail()

    controller = DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=DeadReauthProvider(),
        drive_service_factory=lambda credentials: "service",
        sync_factory=sync_factory,
    )

    with pytest.raises(HomeUnavailableError, match="Drive non disponibile"):
        controller.refresh()


def test_refresh_ritenta_errori_transienti_con_limite(tmp_path):
    provider = FakeProvider()
    calls = []

    def sync_factory(service, folder_id, cache_dir):
        class FlakySync:
            def list_schede(self):
                calls.append("list")
                if len(calls) < 3:
                    raise OSError("connessione resettata")
                return []
        return FlakySync()

    controller = DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=provider, drive_service_factory=lambda credentials: "service",
        sync_factory=sync_factory, retry_sleep=lambda _: None,
    )

    assert controller.refresh() == []
    assert calls == ["list", "list", "list"]


def test_create_non_ritenta_operazione_drive_non_idempotente(tmp_path):
    calls = []

    def sync_factory(service, folder_id, cache_dir):
        class BrokenSync:
            def create_scheda(self, path):
                calls.append("create")
                raise OSError("esito create incerto")
        return BrokenSync()

    controller = DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=FakeProvider(), drive_service_factory=lambda credentials: "service",
        sync_factory=sync_factory, retry_sleep=lambda _: None,
    )

    with pytest.raises(HomeUnavailableError):
        controller.create("nuova")
    assert calls == ["create"]
