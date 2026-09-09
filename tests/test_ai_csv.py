"""AI starter kit: example CSV, prompt template, and Download export.

Everything here must stay Kivy- and Android-free: the tests exercise the pure
module and the controller with an injected fake local store.
"""

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.csv_utils import parse_esercizi_csv
from kivy_app.ai_csv import (COLONNE_ESEMPIO, NOME_CSV_ESEMPIO, PROMPT_TEMPLATE,
                             csv_esempio)
from kivy_app.config import FolderConfigStore, LocalPrefsStore
from kivy_app.controller import DriveHomeController
from kivy_app.local_store import AndroidLocalStore, LocalStoreError


# ------------------------------------------------------------------ ai_csv
def test_csv_esempio_parseggia_come_manifest_reale():
    esercizi = parse_esercizi_csv(io.StringIO(csv_esempio()))
    assert esercizi, "l'esempio non deve essere vuoto"
    for e in esercizi:
        assert e["nome"] and e["spiegazione"] and e["ripetizioni"] and e["recupero"]
        assert e["gruppo"]
    gruppi = [e["gruppo"] for e in esercizi]
    compressi = [g for i, g in enumerate(gruppi) if i == 0 or g != gruppi[i - 1]]
    assert len(compressi) == len(set(compressi)), "i Gruppi vanno in righe consecutive"


def test_prompt_contiene_intestazione_ed_esempio_ufficiosi():
    header = ",".join(COLONNE_ESEMPIO)
    assert header in PROMPT_TEMPLATE
    assert csv_esempio().rstrip() in PROMPT_TEMPLATE, "prompt ed CSV salvato coincidono"
    for regola in ("UTF-8", "doppi apici", "90 SEC", "VideoURL", "DESCRIVI QUI"):
        assert regola in PROMPT_TEMPLATE


def test_csv_esempio_non_aggiunge_colonne_optionals():
    header = csv_esempio().splitlines()[0]
    assert header == ",".join(COLONNE_ESEMPIO)


# ------------------------------------------------------- AndroidLocalStore
class _FakeBridge:
    def __init__(self):
        self.saved = []

    def salvaFile(self, activity, src, nome, kind):
        self.saved.append((src, nome, kind))
        return "content://downloads/pyTrainer/" + nome


class _FakeActivity:
    mActivity = object()


def _store():
    bridge = _FakeBridge()

    def autoclass(name):
        return bridge if name.endswith("StorageBridge") else _FakeActivity

    return AndroidLocalStore(autoclass_factory=autoclass, kind="documenti"), bridge


def test_salva_kind_override_non_cambia_la_destinazione_predefinita(tmp_path):
    store, bridge = _store()
    src = tmp_path / NOME_CSV_ESEMPIO
    src.write_text("x", encoding="utf-8")
    store.salva(src, NOME_CSV_ESEMPIO, kind="download")
    assert bridge.saved == [(str(src), NOME_CSV_ESEMPIO, "download")]
    store.salva(src, "altro.scheda")
    assert bridge.saved[-1][2] == "documenti"


def test_salva_traduce_errore_nativo_anche_con_kind():
    class _Err:
        def salvaFile(self, activity, src, nome, kind):
            return "ERR: permesso negato"

    store = AndroidLocalStore.__new__(AndroidLocalStore)
    store._bridge_cls = _Err()
    store._activity = object()
    store._kind = "documenti"
    with pytest.raises(LocalStoreError, match="permesso"):
        store.salva("/tmp/x.csv", "x.csv", kind="download")


# ---------------------------------------------------------------- controller
class _Store:
    def __init__(self):
        self.calls = []

    def salva(self, src, nome, kind=None):
        self.calls.append((Path(src), nome, kind))
        return f"content://download/{nome}"


def _controller(tmp_path, local_store=None):
    return DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=SimpleNamespace(get_credentials=lambda scopes: "c"),
        drive_service_factory=lambda credentials: "drive",
        sync_factory=object,
        base_dir=tmp_path, local_store=local_store,
        prefs_store=LocalPrefsStore(tmp_path / "prefs.json"),
    )


def test_salva_csv_esempio_android_usa_sempre_download(tmp_path):
    store = _Store()
    controller = _controller(tmp_path, local_store=store)
    etichetta = controller.salva_csv_esempio()
    assert etichetta == f"Download/pyTrainer/{NOME_CSV_ESEMPIO}"
    sorgente, nome, kind = store.calls[0]
    assert kind == "download"
    assert nome == NOME_CSV_ESEMPIO
    assert sorgente.read_text(encoding="utf-8") == csv_esempio()


def test_salva_csv_esempio_pc_scrive_in_downloads(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    monkeypatch.setattr(Path, "home", lambda: casa)
    controller = _controller(tmp_path)
    percorso = controller.salva_csv_esempio()
    file = Path(percorso)
    assert file == casa / "Downloads" / NOME_CSV_ESEMPIO
    assert file.read_text(encoding="utf-8") == csv_esempio()
    # il contenuto deve essere reimportabile dall'editor
    assert parse_esercizi_csv(str(file))
