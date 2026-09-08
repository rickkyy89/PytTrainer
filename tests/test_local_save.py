"""Local save destination + open-from-device + publish-to-Drive behavior.

These modules must stay Kivy-free, so the tests exercise the pure-logic layers
with an injected fake bridge (Android) and the real ``core.scheda_file`` codec.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.drive_sync import RemoteScheda
from core.scheda_file import salva_scheda
from kivy_app.config import AppConfigError, FolderConfigStore, LocalPrefs, LocalPrefsStore
from kivy_app.controller import DriveHomeController
from kivy_app.editor import SchedaEditorController
from kivy_app.local_store import AndroidLocalStore, LocalStoreError


ESERCIZIO = {
    "nome": "Squat", "spiegazione": "Scendi controllando.", "note": "",
    "ripetizioni": "3x12", "recupero": "90 SEC", "gruppo": "Gambe",
    "frame_start": None, "frame_finish": None, "video_url": "",
    "ts_start": None, "ts_finish": None,
}


# ---------------------------------------------------------------- local_store
class _FakeBridge:
    def __init__(self):
        self.saved = []
        self.uris = []
        self.risposta = "content://media/external/documents/pyTrainer/gambe.scheda"

    def salvaFile(self, activity, src, nome, kind):
        self.saved.append((src, nome, kind))
        return self.risposta

    def copiaUri(self, activity, uri, dest_dir):
        self.uris.append((uri, dest_dir))
        return str(Path(dest_dir) / "reimportato.scheda")


class _FakeActivity:
    mActivity = object()


def _store(kind="documenti", risposta="content://x"):
    bridge = _FakeBridge()
    bridge.risposta = risposta

    def autoclass(name):
        return bridge if name.endswith("StorageBridge") else _FakeActivity

    store = AndroidLocalStore(autoclass_factory=autoclass, kind=kind)
    return store, bridge


def test_android_salva_usa_la_destinazione_scelta():
    store, bridge = _store(kind="download")
    esito = store.salva("/cache/gambe.scheda", "gambe.scheda")
    assert esito == "content://x"
    assert bridge.saved == [("/cache/gambe.scheda", "gambe.scheda", "download")]


def test_android_salva_traduce_errore_nativo():
    store, _ = _store(risposta="ERR: permesso negato")
    with pytest.raises(LocalStoreError, match="permesso negato"):
        store.salva("/cache/x.scheda", "x.scheda")


def test_android_importa_copia_content_uri_e_lascia_passare_i_percorsi(tmp_path):
    store, bridge = _store()
    reale = tmp_path / "locale.scheda"
    reale.write_bytes(b"bundle")
    assert store.importa("content://abc", tmp_path).endswith("reimportato.scheda")
    assert bridge.uris == [("content://abc", str(tmp_path))]
    assert store.importa(str(reale), tmp_path) == str(reale)
    with pytest.raises(LocalStoreError):
        store.importa(str(tmp_path / "inesistente.scheda"), tmp_path)


def test_android_etichetta_e_percorso_descrizione():
    store, _ = _store(kind="documenti")
    assert store.etichetta == "Documenti"
    assert store.percorso_descrizione == "Documents/pyTrainer"
    store.set_kind("download")
    assert store.kind == "download"
    assert store.percorso_descrizione == "Download/pyTrainer"
    with pytest.raises(LocalStoreError):
        store.set_kind(" desktop")


# ------------------------------------------------------------------ config
def test_local_prefs_default_when_mancante_o_corrotto(tmp_path):
    path = tmp_path / "local-save.json"
    assert LocalPrefsStore(path).load() == LocalPrefs("documenti")
    path.write_text("{ non json", encoding="utf-8")
    assert LocalPrefsStore(path).load() == LocalPrefs("documenti")
    path.write_text('{"destinazione": "desktop"}', encoding="utf-8")
    assert LocalPrefsStore(path).load() == LocalPrefs("documenti")


def test_local_prefs_roundtrip(tmp_path):
    store = LocalPrefsStore(tmp_path / "local-save.json")
    store.save(LocalPrefs("download"))
    assert store.load() == LocalPrefs("download")
    with pytest.raises(AppConfigError):
        store.save(LocalPrefs("desktop"))


# ------------------------------------------------------------------ editor
def _bundle(tmp_path, nome="gambe.scheda"):
    percorso = tmp_path / nome
    salva_scheda([dict(ESERCIZIO)], str(percorso), titolo=nome[:-len(".scheda")])
    return percorso


def test_editor_salva_locale_specchia_nel_local_store(tmp_path):
    bundle = _bundle(tmp_path)
    store, bridge = _store()
    editor = SchedaEditorController([dict(ESERCIZIO)], percorso_bundle=str(bundle),
                                    local_store=store)
    assert editor.salva(sincronizza=False) is None
    assert editor.non_sincronizzato is True
    assert bridge.saved == [(str(bundle), "gambe.scheda", "documenti")]
    assert editor.ultima_copia_locale == "content://x"


def test_editor_salva_drive_fallito_mantiene_ed_specchia_la_copia(tmp_path):
    bundle = _bundle(tmp_path)
    store, bridge = _store()

    def upload(_):
        raise ConnectionError("Drive giù")

    editor = SchedaEditorController([dict(ESERCIZIO)], percorso_bundle=str(bundle),
                                    upload=upload, local_store=store)
    with pytest.raises(ConnectionError):
        editor.salva(sincronizza=True)
    assert editor.non_sincronizzato is True
    assert bridge.saved, "il fallback deve scrivere la copia visibile"
    assert bundle.exists()  # gli edits restano su disco


def test_editor_copia_locale_non_blocca_il_salvataggio(tmp_path):
    bundle = _bundle(tmp_path)

    class Rotto:
        def salva(self, src, nome):
            raise LocalStoreError("permesso negato")

    editor = SchedaEditorController([dict(ESERCIZIO)], percorso_bundle=str(bundle),
                                    local_store=Rotto())
    assert editor.salva(sincronizza=False) is None
    assert editor.ultima_copia_locale is None
    assert bundle.exists()


def test_editor_destinazione_su_pc_copia_il_bundle(tmp_path):
    bundle = _bundle(tmp_path)
    destinazione = tmp_path / "Scelti" / "mio.scheda"
    editor = SchedaEditorController([dict(ESERCIZIO)], percorso_bundle=str(bundle))
    editor.salva(sincronizza=False, destinazione=str(destinazione))
    assert destinazione.read_bytes() == bundle.read_bytes()
    assert editor.ultima_copia_locale == str(destinazione)


def test_editor_pubblica_lega_drive_e_segna_pubblicato(tmp_path):
    bundle = _bundle(tmp_path)
    editor = SchedaEditorController([dict(ESERCIZIO)], percorso_bundle=str(bundle))
    assert editor.pubblicato_su_drive is False

    remote = RemoteScheda("gambe.scheda", "drive-1", "2026-09-07T00:00:00Z")
    result = editor.pubblica(lambda path: SimpleNamespace(remote=remote))
    assert result.remote is remote
    assert editor.pubblicato_su_drive is True
    assert editor.non_sincronizzato is False


# -------------------------------------------------------------- controller
class _Sync:
    def __init__(self, service, folder_id, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.records = [RemoteScheda("gambe.scheda", "one", "2026-09-07T10:00:00Z")]
        self.updated = []
        self.created = []

    def list_schede(self):
        return self.records

    def create_scheda(self, path):
        self.created.append(Path(path))
        return SimpleNamespace(remote=RemoteScheda(Path(path).name, "new-id", "2026-09-07T10:00:00Z"),
                               created=True)

    def upload_scheda(self, path, file_id=None, force=False):
        self.updated.append((Path(path), file_id, force))
        return SimpleNamespace(remote=RemoteScheda(Path(path).name, file_id, "2026-09-07T10:00:00Z"),
                               created=False)


def _controller(tmp_path, local_store=None):
    store = FolderConfigStore(tmp_path / "folders.json")
    controller = DriveHomeController(
        store, tmp_path / "cache",
        credential_provider=SimpleNamespace(get_credentials=lambda scopes: "c"),
        drive_service_factory=lambda credentials: "drive",
        sync_factory=_Sync,
        local_store=local_store, prefs_store=LocalPrefsStore(tmp_path / "prefs.json"),
    )
    return controller


def test_apri_edit_locale_da_file_reale(tmp_path):
    bundle = _bundle(tmp_path)
    controller = _controller(tmp_path)
    editor = controller.open_for_edit_locale(str(bundle))
    assert editor.pubblicato_su_drive is False
    assert [e["nome"] for e in editor.esercizi] == ["Squat"]


def test_remoto_con_nome_trova_per_nome_anche_senza_estensione(tmp_path):
    controller = _controller(tmp_path)
    assert controller.remoto_con_nome("gambe").id == "one"
    assert controller.remoto_con_nome("gambe.scheda").id == "one"
    assert controller.remoto_con_nome("braccia") is None


def test_pubblica_in_drive_senza_remoto_crea_e_agguancia(tmp_path):
    bundle = _bundle(tmp_path)
    controller = _controller(tmp_path)
    editor = controller.open_for_edit_locale(str(bundle))
    sync = controller._drive()
    controller.pubblica_in_drive(editor, remoto=None)
    assert sync.created and sync.created[-1].name == "gambe.scheda"
    assert editor.pubblicato_su_drive is True


def test_pubblica_in_drive_con_remoto_forza_sovrascrittura(tmp_path):
    bundle = _bundle(tmp_path)
    controller = _controller(tmp_path)
    editor = controller.open_for_edit_locale(str(bundle))
    sync = controller._drive()
    remoto = controller.remoto_con_nome("gambe")
    controller.pubblica_in_drive(editor, remoto=remoto)
    assert sync.updated[-1][1] == "one" and sync.updated[-1][2] is True
    assert editor.pubblicato_su_drive is True


def test_destinazione_locale_si_persiste_e_aggiorna_lo_store(tmp_path):
    store, _ = _store(kind="documenti")
    controller = _controller(tmp_path, local_store=store)
    assert controller.destinazione_locale == "documenti"
    controller.imposta_destinazione_locale("download")
    assert store.kind == "download"
    assert LocalPrefsStore(tmp_path / "prefs.json").load() == LocalPrefs("download")
