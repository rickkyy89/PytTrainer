"""Ticket 10: DriveHomeController open-time check and conflict resolutions."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.drive_sync import RemoteScheda, SyncConflict, UploadResult
from kivy_app.config import FolderConfigStore
from kivy_app.controller import DriveHomeController, HomeUnavailableError


CONFLICT = SyncConflict("fid", "gambe.scheda", "2026-09-02T12:00:00Z",
                        "2026-09-02T11:00:00Z", "2026-09-02T10:00:00Z")


class RecordingSync:
    def __init__(self, service, folder_id, cache_dir, *, conflict=None, remote_names=None):
        self.cache_dir = Path(cache_dir)
        self.conflict = conflict
        self.remote_names = remote_names or ["gambe.scheda"]
        self.uploads = []
        self.downloads = []
        self.creates = []

    def list_schede(self):
        return [RemoteScheda(name, "id-" + name, "2026-09-02T10:00:00Z")
                for name in self.remote_names]

    def check_conflict(self, local_path, file_id=None):
        return self.conflict

    def upload_scheda(self, path, file_id=None, force=False):
        self.uploads.append((Path(path), file_id, force))
        return UploadResult(RemoteScheda(Path(path).name, file_id, "2026-09-02T13:00:00Z"),
                            created=False)

    def download_scheda(self, file_id, name=None):
        self.downloads.append((file_id, name))
        return self.cache_dir / name

    def create_scheda(self, path):
        self.creates.append(Path(path))
        return UploadResult(RemoteScheda(Path(path).name, "dup-id", "2026-09-02T13:00:00Z"),
                            created=True)


def make_home(tmp_path, sync_kwargs=None):
    instances = []

    def sync_factory(service, folder_id, cache_dir):
        sync = RecordingSync(service, folder_id, cache_dir, **(sync_kwargs or {}))
        instances.append(sync)
        return sync

    controller = DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=SimpleNamespace(get_credentials=lambda scopes: "creds"),
        drive_service_factory=lambda creds: "service",
        sync_factory=sync_factory,
    )
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)
    return controller, instances


def test_check_conflict_nulla_da_fare_se_il_bundle_non_e_in_cache(tmp_path):
    controller, instances = make_home(tmp_path)

    assert controller.check_conflict(RemoteScheda("gambe.scheda", "fid", "t")) is None
    assert instances == []  # nessun download/ Drive richiesto


def test_check_conflict_delega_percorso_e_id_al_drive_sync(tmp_path):
    controller, instances = make_home(tmp_path, {"conflict": CONFLICT})
    (tmp_path / "cache" / "gambe.scheda").write_bytes(b"local")

    conflitto = controller.check_conflict(RemoteScheda("gambe.scheda", "fid", "t"))

    assert conflitto is CONFLICT


def test_risoluzione_locale_forza_upload_sul_file_id_aperto(tmp_path):
    controller, instances = make_home(tmp_path)
    (tmp_path / "cache" / "gambe.scheda").write_bytes(b"local")

    risultato = controller.resolve_conflict(CONFLICT, choice="locale")

    assert isinstance(risultato, UploadResult)
    assert instances[0].uploads == [(tmp_path / "cache" / "gambe.scheda", "fid", True)]


def test_risoluzione_remota_riscarica_il_bundle(tmp_path):
    controller, instances = make_home(tmp_path)

    percorso = controller.resolve_conflict(CONFLICT, choice="remota")

    assert instances[0].downloads == [("fid", "gambe.scheda")]
    assert percorso == tmp_path / "cache" / "gambe.scheda"


def test_risoluzione_duplicata_copia_rinomina_carica_e_ripristina(tmp_path):
    controller, instances = make_home(tmp_path)
    originale = tmp_path / "cache" / "gambe.scheda"
    originale.write_bytes(b"local edit")

    risultato = controller.resolve_conflict(CONFLICT, choice="duplicata")

    copia = tmp_path / "cache" / "gambe (2).scheda"
    assert instances[0].creates == [copia]
    assert copia.read_bytes() == b"local edit"
    assert instances[0].downloads == [("fid", "gambe.scheda")]
    assert risultato.created is True

    # una seconda duplicazione incrementa il suffisso
    controller._duplicate_path("gambe.scheda")
    copia.touch()
    assert controller._duplicate_path("gambe.scheda").name == "gambe (3).scheda"


def test_risoluzione_locale_usa_il_percorso_aperto_se_il_remoto_e_stato_rinominato(tmp_path):
    controller, instances = make_home(tmp_path)
    aperto = tmp_path / "cache" / "vecchio_nome.scheda"
    aperto.write_bytes(b"local edit")
    rinominato = SyncConflict("fid", "nuovo_nome.scheda", "2026-09-02T12:00:00Z",
                              "2026-09-02T11:00:00Z", "2026-09-02T10:00:00Z")

    controller.resolve_conflict(rinominato, choice="locale", local_path=aperto)

    assert instances[0].uploads == [(aperto, "fid", True)]

    instances[0].creates.clear()
    controller.resolve_conflict(rinominato, choice="duplicata", local_path=aperto)
    assert instances[0].creates == [tmp_path / "cache" / "nuovo_nome (2).scheda"]


def test_risoluzione_duplicata_evita_nomi_gia_usati_su_drive(tmp_path):
    controller, instances = make_home(
        tmp_path, {"remote_names": ["gambe.scheda", "gambe (2).scheda", "gambe (3).scheda"]})
    (tmp_path / "cache" / "gambe.scheda").write_bytes(b"local edit")

    controller.resolve_conflict(CONFLICT, choice="duplicata")

    assert instances[0].creates == [tmp_path / "cache" / "gambe (4).scheda"]


def test_scelta_sconosciuta_o_drive_giu_risalgono_come_errore_utente(tmp_path):
    controller, instances = make_home(tmp_path)
    (tmp_path / "cache" / "gambe.scheda").write_bytes(b"x")

    with pytest.raises(HomeUnavailableError):
        controller.resolve_conflict(CONFLICT, choice="last-write-wins")

    instances[0].upload_scheda = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
    with pytest.raises(HomeUnavailableError, match="Drive non disponibile"):
        controller.resolve_conflict(CONFLICT, choice="locale")
