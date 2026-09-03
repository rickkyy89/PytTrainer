"""DocExportController behavior (ticket 08); no Kivy, no network."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.drive_sync import SyncConflict
from kivy_app.editor import SchedaEditorController
from kivy_app.export import DocExportController, DocExportError


def make_editor(tmp_path, pronti=2, rotti=1, upload_result=None):
    esercizi = []
    for i in range(pronti):
        a = tmp_path / f"e{i}_start.jpg"
        b = tmp_path / f"e{i}_finish.jpg"
        a.write_bytes(b"x")
        b.write_bytes(b"y")
        esercizi.append({"nome": f"E{i}", "spiegazione": "", "note": "",
                         "ripetizioni": "3x10", "recupero": "60 SEC", "gruppo": "",
                         "video_url": "", "ts_start": None, "ts_finish": None,
                         "frame_start": str(a), "frame_finish": str(b)})
    for i in range(rotti):
        esercizi.append({"nome": f"Rotto{i}", "spiegazione": "", "note": "",
                         "ripetizioni": "", "recupero": "", "gruppo": "",
                         "video_url": "", "ts_start": None, "ts_finish": None,
                         "frame_start": None, "frame_finish": None})
    return SchedaEditorController(
        esercizi, percorso_bundle=str(tmp_path / "my.scheda"),
        cartella_lavoro=str(tmp_path / "my.work"), titolo="My",
        save_scheda=lambda esercizi_, path, state_path=None, titolo=None: Path(path).write_bytes(b"b"),
        upload=lambda path: upload_result,
    )


def make_export(tmp_path, **kwargs):
    editor = kwargs.pop("editor", None) or make_editor(tmp_path)
    created = {}

    def creator(esercizi, titolo, state_path=None, credential_provider=None, base_dir=None):
        created.update(esercizi=[e["nome"] for e in esercizi], titolo=titolo,
                       state_path=state_path, cp=credential_provider, bd=base_dir)
        Path(state_path).write_text('{"doc_id": "d1", "esercizi": []}', encoding="utf-8")
        return {"document_id": "d1", "url": "https://docs/d1",
                "esercizi_inseriti": created["esercizi"], "documento_rigenerato": False}

    controller = DocExportController(
        editor, credential_provider="CP", base_dir=tmp_path, creator=creator,
        stato_loader=lambda path: _leggi(path), **kwargs)
    return controller, editor, created


def _leggi(path):
    import json
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def test_riepilogo_conta_pronti_totali_e_titolo(tmp_path):
    controller, _, _ = make_export(tmp_path)

    riepilogo = controller.riepilogo()

    assert (riepilogo.pronti, riepilogo.totali, riepilogo.titolo) == (2, 3, "My")


def test_riepilogo_senza_titolo_usa_il_nome_del_bundle(tmp_path):
    editor = make_editor(tmp_path)
    editor._titolo = None
    controller, _, _ = make_export(tmp_path, editor=editor)

    assert controller.riepilogo().titolo == "my"


def test_genera_passa_pronti_state_path_provider_e_salva_stato(tmp_path):
    controller, editor, created = make_export(tmp_path)

    risultato = controller.genera()

    assert created["esercizi"] == ["E0", "E1"]
    assert created["titolo"] == "My"
    assert created["state_path"] == str(tmp_path / "my.work" / "state.json")
    assert created["cp"] == "CP"
    assert created["bd"] == tmp_path
    assert risultato["url"] == "https://docs/d1"
    assert editor.sporco is False  # editor.salva ha completato (upload None)


def test_genera_blocca_scheda_senza_esercizi_pronti(tmp_path):
    editor = make_editor(tmp_path, pronti=0)
    controller, _, _ = make_export(tmp_path, editor=editor)

    with pytest.raises(DocExportError, match="Nessun esercizio pronto"):
        controller.genera()


def test_progresso_legge_i_checkpoint_del_state(tmp_path):
    controller, _, _ = make_export(tmp_path)
    assert controller.progresso() == (0, 2)

    controller.genera()

    # dopo genera: lo stato finto ha 0 esercizi; simuliamo il worker a meta'
    Path(controller._state_path).write_text(
        '{"doc_id":"d1","esercizi":[{"nome":"E0","slug":"e0"},'
        '{"nome":"E1","slug":"e1"}]}', encoding="utf-8")
    assert controller.progresso() == (2, 2)


def test_genera_in_conflitto_propaga_esito_e_lascia_retry_su_salva(tmp_path):
    conflict = SyncConflict("x", "my.scheda", "2026-09-01T00:00:00Z",
                            "2026-09-02T00:00:00Z", "2026-08-31T00:00:00Z")
    editor = make_editor(tmp_path, upload_result=conflict)
    controller, _, _ = make_export(tmp_path, editor=editor)

    risultato = controller.genera()

    assert risultato["salvataggio"] is conflict
    # Bundle locale già scritto: nessun edit pendente, ma un nuovo "Salva"
    # dell'editor ritenta l'upload (contract del ticket 06/10).
    assert editor.sporco is False
    assert editor.salva() is conflict
