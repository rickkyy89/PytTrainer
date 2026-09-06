"""DocExportController behavior (ticket 08); no Kivy, no network."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.drive_sync import SyncConflict
from kivy_app.editor import SchedaEditorController
from kivy_app.export import DocExportController, DocExportError, PdfExportError


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
    credential_provider = kwargs.pop("credential_provider", "CP")
    created = {}

    def creator(esercizi, titolo, state_path=None, credential_provider=None, base_dir=None):
        created.update(esercizi=[e["nome"] for e in esercizi], titolo=titolo,
                       state_path=state_path, cp=credential_provider, bd=base_dir)
        Path(state_path).write_text('{"doc_id": "d1", "esercizi": []}', encoding="utf-8")
        return {"document_id": "d1", "url": "https://docs/d1",
                "esercizi_inseriti": created["esercizi"], "documento_rigenerato": False}

    controller = DocExportController(
        editor, credential_provider=credential_provider, base_dir=tmp_path, creator=creator,
        stato_loader=lambda path: _leggi(path), **kwargs)
    return controller, editor, created


class _ExportRequest:
    def __init__(self, content):
        self.content = content

    def execute(self):
        return self.content


class _DriveFiles:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def export(self, **kwargs):
        self.calls.append(kwargs)
        return _ExportRequest(self.content)


class _Drive:
    def __init__(self, content=b"%PDF-1.7\nbody"):
        self.files_api = _DriveFiles(content)

    def files(self):
        return self.files_api


class _Credentials:
    def __init__(self):
        self.scopes = []

    def get_credentials(self, scopes):
        self.scopes.append(scopes)
        return "credentials"


class _RefreshingCredentials(_Credentials):
    def __init__(self, refresh_result=True):
        super().__init__()
        self.refresh_result = refresh_result
        self.refresh_calls = 0

    def riautentica(self):
        self.refresh_calls += 1
        return self.refresh_result


class _HttpErrorLike(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.resp = type("Response", (), {"status": status})()


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


def test_genera_passa_snapshot_isolato_all_creator(tmp_path):
    editor = make_editor(tmp_path)
    visti = []

    def creator(esercizi, titolo, state_path=None, credential_provider=None, base_dir=None):
        visti.extend(esercizi)
        return {"document_id": "d", "url": "u", "esercizi_inseriti": [],
                "documento_rigenerato": False}

    controller, _, _ = make_export(tmp_path, editor=editor)
    controller._creator = creator

    controller.genera()

    assert all(d is not e for d, e in zip(visti, editor.esercizi[:2]))
    editor.esercizi[0]["nome"] = "Mutato dopo lo start"
    assert visti[0]["nome"] == "E0"  # la generazione lavora sullo snapshot


def test_errore_di_generazione_persiste_il_checkpoint_nel_bundle(tmp_path):
    editor = make_editor(tmp_path)

    def creator(esercizi, titolo, state_path=None, credential_provider=None, base_dir=None):
        from core.docs_helper import salva_stato
        salva_stato(state_path, {"doc_id": "d1", "titolo": titolo,
                                 "esercizi": [{"nome": "E0", "slug": "e0"}]})
        raise OSError("drive perso a meta')")

    bundle = Path(tmp_path / "my.scheda")
    controller, _, _ = make_export(tmp_path, editor=editor)
    controller._creator = creator
    controller._state_path = None
    editor._upload = lambda path: bundle.write_bytes(b"zip") and None

    with pytest.raises(OSError):
        controller.genera()

    assert bundle.exists()  # il bundle e' stato riscritto con lo stato parziale


def test_salva_stato_e_atomico_e_carica_stato_riapre(tmp_path):
    from core.docs_helper import carica_stato, salva_stato

    stato = tmp_path / "work" / "state.json"
    salva_stato(str(stato), {"doc_id": "x", "esercizi": [{"slug": "a"}]})

    assert carica_stato(str(stato))["doc_id"] == "x"
    assert not list(tmp_path.glob("*.tmp"))


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


def test_esporta_pdf_usa_provider_drive_e_scrittura_atomica(tmp_path):
    credentials = _Credentials()
    drive = _Drive()
    costruzioni = []
    controller, _, _ = make_export(
        tmp_path,
        credential_provider=credentials,
        drive_service_factory=lambda creds: costruzioni.append(creds) or drive,
        pdf_cache_dir=tmp_path / "pdf-cache",
    )

    path = controller.esporta_pdf("doc-123")

    assert path == tmp_path / "pdf-cache" / "My.pdf"
    assert path.read_bytes() == b"%PDF-1.7\nbody"
    assert drive.files_api.calls == [
        {"fileId": "doc-123", "mimeType": "application/pdf"}
    ]
    assert costruzioni == ["credentials"]
    assert any("drive" in scope for scope in credentials.scopes[0])
    assert not list((tmp_path / "pdf-cache").glob("*.tmp"))


@pytest.mark.parametrize("content", [b"", "not bytes", b"not-a-pdf"])
def test_esporta_pdf_non_pubblica_risposte_drive_invalide(tmp_path, content):
    controller, _, _ = make_export(
        tmp_path,
        credential_provider=_Credentials(),
        drive_service_factory=lambda _: _Drive(content),
        pdf_cache_dir=tmp_path / "pdf-cache",
    )

    with pytest.raises(PdfExportError, match="PDF valido"):
        controller.esporta_pdf("doc-123")

    assert not list((tmp_path / "pdf-cache").glob("*.pdf"))


def test_esporta_pdf_non_nasconde_un_fallimento_drive(tmp_path):
    class BrokenRequest:
        def execute(self):
            raise OSError("rete assente")

    class BrokenDrive:
        def files(self):
            return self

        def export(self, **kwargs):
            return BrokenRequest()

    controller, _, _ = make_export(
        tmp_path,
        credential_provider=_Credentials(),
        drive_service_factory=lambda _: BrokenDrive(),
        pdf_cache_dir=tmp_path / "pdf-cache",
    )

    with pytest.raises(PdfExportError, match="rete assente"):
        controller.esporta_pdf("doc-123")


@pytest.mark.parametrize("status", [401, 403])
def test_esporta_pdf_riautentica_e_ritenta_una_volta_su_errore_auth(tmp_path, status):
    credentials = _RefreshingCredentials()
    attempts = []

    class Request:
        def execute(self):
            attempts.append("export")
            if len(attempts) == 1:
                raise _HttpErrorLike(status)
            return b"%PDF-1.7\nbody"

    class Drive:
        def files(self):
            return self

        def export(self, **kwargs):
            return Request()

    services = []
    controller, _, _ = make_export(
        tmp_path,
        credential_provider=credentials,
        drive_service_factory=lambda creds: services.append(creds) or Drive(),
        pdf_cache_dir=tmp_path / "pdf-cache",
    )

    assert controller.esporta_pdf("doc-123").read_bytes().startswith(b"%PDF-")
    assert attempts == ["export", "export"]
    assert credentials.refresh_calls == 1
    assert len(credentials.scopes) == 2
    assert len(services) == 2


def test_esporta_pdf_non_ritenta_due_volte_se_il_retry_auth_fallisce(tmp_path):
    credentials = _RefreshingCredentials()
    attempts = []

    class BrokenDrive:
        def files(self):
            return self

        def export(self, **kwargs):
            class Request:
                def execute(self):
                    attempts.append("export")
                    raise _HttpErrorLike(401)
            return Request()

    controller, _, _ = make_export(
        tmp_path,
        credential_provider=credentials,
        drive_service_factory=lambda _: BrokenDrive(),
        pdf_cache_dir=tmp_path / "pdf-cache",
    )

    with pytest.raises(PdfExportError, match="HTTP 401"):
        controller.esporta_pdf("doc-123")

    assert attempts == ["export", "export"]
    assert credentials.refresh_calls == 1


@pytest.mark.parametrize("title", ["CON", "nul", "COM1", "Lpt9", "CON.txt", "NUL .report"])
def test_esporta_pdf_evade_i_nomi_riservati_windows(tmp_path, title):
    editor = make_editor(tmp_path)
    editor._titolo = title
    controller, _, _ = make_export(
        tmp_path,
        editor=editor,
        credential_provider=_Credentials(),
        drive_service_factory=lambda _: _Drive(),
        pdf_cache_dir=tmp_path / "pdf-cache",
    )

    path = controller.esporta_pdf("doc-123")

    assert path.name.startswith("_")
    assert path.suffix == ".pdf"


def test_esporta_pdf_limita_il_nome_senza_spezzare_unicode_o_estensione(tmp_path):
    editor = make_editor(tmp_path)
    editor._titolo = "Allenamento 🏋️" * 100
    controller, _, _ = make_export(
        tmp_path,
        editor=editor,
        credential_provider=_Credentials(),
        drive_service_factory=lambda _: _Drive(),
        pdf_cache_dir=tmp_path / "pdf-cache",
    )

    path = controller.esporta_pdf("doc-123")

    assert len(path.name.encode("utf-8")) <= 180
    assert path.suffix == ".pdf"
    assert path.read_bytes().startswith(b"%PDF-")
