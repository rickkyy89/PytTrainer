"""Editor controller behavior; these tests never import Kivy."""

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
from kivy_app.editor import EditorValidationError, SchedaEditorController


def make_editor(esercizi=None, **kwargs):
    esercizi = esercizi if esercizi is not None else [
        {"nome": "Squat", "spiegazione": "Scendi.", "note": "Tieni la schiena.",
         "ripetizioni": "3x12", "recupero": "90 SEC", "gruppo": "Gambe",
         "video_url": "", "ts_start": None, "ts_finish": None,
         "frame_start": None, "frame_finish": None},
        {"nome": "Affondo", "spiegazione": "Passo lungo.", "note": "",
         "ripetizioni": "3x10", "recupero": "60 SEC", "gruppo": "Gambe",
         "video_url": "", "ts_start": None, "ts_finish": None,
         "frame_start": None, "frame_finish": None},
    ]
    kwargs.setdefault("percorso_bundle", "scheda.scheda")
    return SchedaEditorController(esercizi, **kwargs)


def test_aggiorna_modifies_only_allowed_fields_and_marks_dirty():
    editor = make_editor()
    assert editor.sporco is False

    editor.aggiorna(0, nome="Squat bilanciere", gruppo="Spinte")

    assert editor.sporco is True
    assert editor.esercizi[0]["nome"] == "Squat bilanciere"
    assert editor.esercizi[0]["gruppo"] == "Spinte"
    assert editor.esercizi[0]["ripetizioni"] == "3x12"
    with pytest.raises(EditorValidationError, match="Campo non modificabile"):
        editor.aggiorna(0, frame_start="x.jpg")
    with pytest.raises(EditorValidationError, match="Indice esercizio non valido"):
        editor.aggiorna(9, nome="X")


def test_add_remove_and_reorder_keep_list_order_and_dirty_flag():
    editor = make_editor()

    indice = editor.aggiungi(dopo=0)
    assert indice == 1
    assert editor.esercizi[1]["nome"] == ""
    editor.aggiorna(1, nome="Pressa")

    assert [e["nome"] for e in editor.esercizi] == ["Squat", "Pressa", "Affondo"]
    assert editor.sposta(2, -1) == 1
    assert [e["nome"] for e in editor.esercizi] == ["Squat", "Affondo", "Pressa"]
    assert editor.sposta(0, -1) == 0

    editor.rimuovi(0)
    assert [e["nome"] for e in editor.esercizi] == ["Affondo", "Pressa"]
    with pytest.raises(EditorValidationError):
        editor.rimuovi(5)


def test_editor_undo_redo_covers_mixed_mutations_and_new_branch():
    editor = make_editor()
    editor.aggiorna(0, nome="Squat profondo")
    editor.aggiungi()
    editor.aggiorna(2, nome="Pressa")
    editor.sposta(2, -1)
    assert [e["nome"] for e in editor.esercizi] == ["Squat profondo", "Pressa", "Affondo"]

    assert editor.undo() is True
    assert [e["nome"] for e in editor.esercizi] == ["Squat profondo", "Affondo", "Pressa"]
    assert editor.undo() is True
    assert [e["nome"] for e in editor.esercizi] == ["Squat profondo", "Affondo", ""]
    assert editor.redo() is True
    assert editor.esercizi[2]["nome"] == "Pressa"

    editor.aggiorna(0, note="Nuova versione")
    assert editor.can_redo is False
    assert editor.redo() is False
    assert editor.esercizi[0]["note"] == "Nuova versione"


def test_editor_history_is_capped_at_twenty_actions():
    editor = make_editor()
    for indice in range(21):
        editor.aggiorna(0, note=str(indice))

    assert editor.can_undo is True
    assert editor.cronologia_dimensione == 20
    for _ in range(20):
        assert editor.undo() is True
    assert editor.undo() is False
    assert editor.esercizi[0]["note"] == "0"


def test_editor_failed_mutation_does_not_enter_history():
    editor = make_editor()
    with pytest.raises(EditorValidationError):
        editor.importa_esercizi([], posizione=99)
    assert editor.can_undo is False
    assert [e["nome"] for e in editor.esercizi] == ["Squat", "Affondo"]


def test_gruppi_esistenti_and_duplicati_slug_report_editor_state():
    editor = make_editor()
    editor.aggiungi()
    editor.aggiorna(2, nome="Squat", gruppo="")

    assert editor.gruppi_esistenti() == ["Gambe"]
    assert editor.duplicati_slug() == {"squat": [0, 2]}


def test_importa_csv_sostituisce_o_aggiunge_esercizi(tmp_path):
    csv_path = tmp_path / "import.csv"
    csv_path.write_text(
        "Nome,Spiegazione,Note,Ripetizioni,Recupero\n"
        "Stacco,Tira.,,3x8,120 SEC\n"
        "Calf,Solleva.,,4x15,45 SEC\n",
        encoding="utf-8",
    )
    editor = make_editor()

    assert editor.importa_csv(str(csv_path)) == 2
    assert [e["nome"] for e in editor.esercizi] == ["Squat", "Affondo", "Stacco", "Calf"]

    assert editor.importa_csv(str(csv_path), sostituisci=True) == 2
    assert [e["nome"] for e in editor.esercizi] == ["Stacco", "Calf"]


def test_importa_csv_invalid_file_raises_validation_error(tmp_path):
    broken = tmp_path / "broken.csv"
    broken.write_text("Nome,Spiegazione\n", encoding="utf-8")
    editor = make_editor()

    with pytest.raises(EditorValidationError, match="CSV non valido"):
        editor.importa_csv(str(broken))


def test_salva_rewrites_bundle_keeps_title_and_clears_dirty(tmp_path):
    saved = {}

    def fake_save(esercizi, percorso, state_path=None, titolo=None):
        saved.update(esercizi=list(esercizi), percorso=percorso,
                     state_path=state_path, titolo=titolo)

    upload_calls = []
    editor = make_editor(percorso_bundle=str(tmp_path / "s.scheda"),
                         cartella_lavoro=str(tmp_path / "s.work"),
                         titolo="Gambe A", save_scheda=fake_save,
                         upload=lambda path: upload_calls.append(path))
    (tmp_path / "s.work").mkdir()
    (tmp_path / "s.work" / "state.json").write_text("{}", encoding="utf-8")

    editor.aggiorna(0, ripetizioni="4x10")
    result = editor.salva()

    assert result is None
    assert saved["titolo"] == "Gambe A"
    assert saved["state_path"] == str(tmp_path / "s.work" / "state.json")
    assert saved["esercizi"][0]["ripetizioni"] == "4x10"
    assert upload_calls == [str(tmp_path / "s.scheda")]
    assert editor.sporco is False


def test_salva_senza_stato_non_passa_state_path(tmp_path):
    captured = {}
    editor = make_editor(percorso_bundle=str(tmp_path / "s.scheda"),
                         cartella_lavoro=str(tmp_path / "assente.work"),
                         save_scheda=lambda *a, **k: captured.update(k),
                         upload=None)

    editor.aggiungi()
    editor.aggiorna(2, nome="Nuovo")
    editor.salva()

    assert captured["state_path"] is None


def test_salva_blocca_esercizi_senza_nome():
    editor = make_editor()
    editor.aggiungi()

    with pytest.raises(EditorValidationError, match="non ha un nome"):
        editor.salva()


def test_salva_propaga_il_conflitto_e_mantiene_le_modifiche_pendenti():
    conflict = SyncConflict("id1", "s.scheda", "2026-09-01T00:00:00Z",
                            "2026-09-02T00:00:00Z", "2026-08-31T00:00:00Z")
    editor = make_editor(save_scheda=lambda *a, **k: None,
                         upload=lambda path: conflict)

    editor.aggiorna(0, note="Esplosive.")
    assert editor.salva() is conflict
    assert editor.sporco is True


def test_upload_fallito_lascia_il_bundle_salvato_e_lo_stato_sporco(tmp_path):
    bundle = tmp_path / "s.scheda"
    editor = make_editor(percorso_bundle=str(bundle),
                         save_scheda=lambda esercizi, path, state_path=None, titolo=None: Path(path).write_bytes(b"zip"),
                         upload=lambda path: (_ for _ in ()).throw(OSError("offline")))

    editor.aggiorna(0, note="Esplosive.")
    with pytest.raises(OSError):
        editor.salva()
    assert bundle.exists()
    assert editor.sporco is True


def test_sposta_alla_riordina_senza_spostare_gli_altri():
    editor = make_editor()
    editor.aggiungi()
    editor.aggiorna(2, nome="Panca")

    assert editor.sposta_alla(0, 2) == 2
    assert [e["nome"] for e in editor.esercizi] == ["Affondo", "Panca", "Squat"]
    assert editor.sposta_alla(1, 0) == 0
    assert [e["nome"] for e in editor.esercizi] == ["Panca", "Affondo", "Squat"]
    assert editor.sposta_alla(1, 1) == 1
    assert editor.sporco is True


def test_sposta_alla_valida_indici():
    editor = make_editor()
    with pytest.raises(EditorValidationError, match="Posizione di destinazione"):
        editor.sposta_alla(0, 2)
    with pytest.raises(EditorValidationError, match="Indice esercizio non valido"):
        editor.sposta_alla(9, 0)


def test_importa_esercizi_in_posizione():
    editor = make_editor()
    nuovo = {"nome": "Nuovo", "spiegazione": "", "note": "", "ripetizioni": "",
             "recupero": "", "gruppo": ""}

    editor.importa_esercizi([dict(nuovo)], posizione=1)

    assert [e["nome"] for e in editor.esercizi] == ["Squat", "Nuovo", "Affondo"]
    with pytest.raises(EditorValidationError, match="Posizione di inserimento"):
        editor.importa_esercizi([dict(nuovo)], posizione=99)


def test_importa_csv_in_posizione(tmp_path):
    csv_path = tmp_path / "import.csv"
    csv_path.write_text(
        "Nome,Spiegazione,Note,Ripetizioni,Recupero\nStacco,Tira.,,3x8,120 SEC\n",
        encoding="utf-8",
    )
    editor = make_editor()

    assert editor.importa_csv(str(csv_path), posizione=0) == 1
    assert [e["nome"] for e in editor.esercizi] == ["Stacco", "Squat", "Affondo"]


def test_salva_solo_locale_non_carica_su_drive(tmp_path):
    caricati = []
    editor = make_editor(percorso_bundle=str(tmp_path / "s.scheda"),
                         save_scheda=lambda e, p, state_path=None, titolo=None: Path(p).write_bytes(b"zip"),
                         upload=lambda path: caricati.append(path))

    editor.aggiorna(0, note="Esplosive.")
    assert editor.salva(sincronizza=False) is None

    assert (tmp_path / "s.scheda").exists()
    assert caricati == []
    assert editor.sporco is False
    assert editor.non_sincronizzato is True

    editor.salva()
    assert caricati == [str(tmp_path / "s.scheda")]
    assert editor.non_sincronizzato is False


def test_conflitto_marca_non_sincronizzato_e_conferma_azzera():
    conflict = SyncConflict("id1", "s.scheda", "2026-09-01T00:00:00Z",
                            "2026-09-02T00:00:00Z", "2026-08-31T00:00:00Z")
    editor = make_editor(save_scheda=lambda *a, **k: None,
                         upload=lambda path: conflict)

    editor.aggiorna(0, note="X")
    assert editor.salva() is conflict
    assert editor.non_sincronizzato is True
    editor.conferma_salvataggio()
    assert editor.non_sincronizzato is False
    assert editor.sporco is False


class FakeSync:
    def __init__(self, service, folder_id, cache_dir):
        self.records = [RemoteScheda("gambe.scheda", "one", "2026-09-02T10:00:00Z"),
                        RemoteScheda("braccia.scheda", "two", "2026-09-02T10:00:00Z")]
        self.cache_dir = Path(cache_dir)
        self.uploads = []

    def list_schede(self):
        return self.records

    def download_scheda(self, file_id, name):
        return self.cache_dir / name

    def upload_scheda(self, path, file_id=None):
        self.uploads.append((Path(path), file_id))
        return UploadResult(RemoteScheda(Path(path).name, file_id or "one", "2026-09-03T10:00:00Z"),
                            created=False)


def make_home(tmp_path, load_side_effect=None):
    instances = []

    def sync_factory(service, folder_id, cache_dir):
        sync = FakeSync(service, folder_id, cache_dir)
        instances.append(sync)
        return sync

    def loader(path):
        return ([{"nome": "Squat", "spiegazione": "Scendi.", "note": "",
                  "ripetizioni": "3x12", "recupero": "90 SEC", "gruppo": "Gambe",
                  "frame_start": None, "frame_finish": None}], f"{path}.work")

    controller = DriveHomeController(
        FolderConfigStore(tmp_path / "folders.json"), tmp_path / "cache",
        credential_provider=SimpleNamespace(get_credentials=lambda scopes: "creds"),
        drive_service_factory=lambda credentials: "service",
        sync_factory=sync_factory, load_scheda=loader,
        save_scheda=lambda esercizi, percorso, state_path=None, titolo=None: Path(percorso).write_bytes(b"zip"),
    )
    return controller, instances


def test_open_for_edit_returns_editor_wired_to_drive_upload(tmp_path):
    controller, instances = make_home(tmp_path)
    remote = controller.refresh()[0]

    editor = controller.open_for_edit(remote)

    assert isinstance(editor, SchedaEditorController)
    assert [e["nome"] for e in editor.esercizi] == ["Squat"]
    editor.aggiorna(0, nome="Squat profondo")
    result = editor.salva()
    assert result.remote.id == "one"
    assert instances[0].uploads == [(tmp_path / "cache" / "gambe.scheda", "one")]


def test_import_remote_into_sostituisce_o_aggiunge_via_drive(tmp_path):
    controller, _ = make_home(tmp_path)
    editor = controller.open_for_edit(controller.refresh()[0])
    prima = [e["nome"] for e in editor.esercizi]

    count = controller.import_remote_into(editor, controller.refresh()[1], sostituisci=False)
    assert count == 1 and [e["nome"] for e in editor.esercizi] == prima + ["Squat"]
    assert editor.sporco is True

    count = controller.import_remote_into(editor, controller.refresh()[1], sostituisci=True)
    assert [e["nome"] for e in editor.esercizi] == ["Squat"]


def test_import_remote_into_in_posizione(tmp_path):
    controller, _ = make_home(tmp_path)
    editor = controller.open_for_edit(controller.refresh()[0])
    editor.aggiungi()
    editor.aggiorna(1, nome="Panca")

    controller.import_remote_into(editor, controller.refresh()[1],
                                  sostituisci=False, posizione=1)

    assert [e["nome"] for e in editor.esercizi] == ["Squat", "Squat", "Panca"]


def test_import_remote_into_errori_drive_diventano_disponibilita(tmp_path, monkeypatch):
    controller, instances = make_home(tmp_path)
    editor = controller.open_for_edit(controller.refresh()[0])
    instances[0].download_scheda = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))

    with pytest.raises(HomeUnavailableError, match="Drive non disponibile"):
        controller.import_remote_into(editor, controller.refresh()[1], sostituisci=True)
