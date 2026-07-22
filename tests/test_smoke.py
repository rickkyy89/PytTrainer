"""
Test 'smoke' per il progetto Workout Sheet Automator.

Non richiedono rete né credenziali Google reali: tutte le chiamate esterne
(YouTube, Google Docs/Drive API) sono mockate o evitate. L'unico strumento
esterno eventualmente usato è ffmpeg (se presente in PATH) per un test reale
di estrazione frame da un video sintetico generato localmente.
"""

import ast
import compileall
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Rendiamo importabili i moduli del progetto (root della repo) indipendentemente
# da dove viene lanciato pytest.
RADICE_PROGETTO = Path(__file__).resolve().parent.parent
if str(RADICE_PROGETTO) not in sys.path:
    sys.path.insert(0, str(RADICE_PROGETTO))

import csv_utils  # noqa: E402
import google_docs_helper  # noqa: E402
import video_helper  # noqa: E402
from csv_utils import parse_esercizi_csv  # noqa: E402
from google_docs_helper import create_workout_document  # noqa: E402
from video_helper import FrameExtractionError, extract_frame  # noqa: E402


# ---------------------------------------------------------------------------
# Test di import / validità sintattica dei moduli
# ---------------------------------------------------------------------------

def test_import_moduli_principali():
    """I moduli 'puri' del progetto devono essere importabili senza errori."""
    assert hasattr(video_helper, "search_youtube")
    assert hasattr(video_helper, "get_stream_url")
    assert hasattr(video_helper, "extract_frame")
    assert hasattr(video_helper, "extract_start_finish_frames")
    assert hasattr(google_docs_helper, "create_workout_document")
    assert hasattr(google_docs_helper, "get_credentials")
    assert hasattr(csv_utils, "parse_esercizi_csv")


def test_app_py_sintatticamente_valido():
    """
    app.py usa Streamlit e non va importato direttamente in un ambiente di test
    senza contesto Streamlit attivo: ne verifichiamo comunque la correttezza
    sintattica con ast.parse/compile, e ci assicuriamo che tutta la logica sia
    incapsulata in main() così un eventuale import non eseguirebbe nulla.
    """
    percorso_app = RADICE_PROGETTO / "app.py"
    codice_sorgente = percorso_app.read_text(encoding="utf-8")

    albero = ast.parse(codice_sorgente, filename=str(percorso_app))
    assert albero is not None

    # compile() verifica ulteriormente che il bytecode sia generabile.
    compilato = compile(codice_sorgente, str(percorso_app), "exec")
    assert compilato is not None

    # Verifichiamo che la logica applicativa sia incapsulata in una funzione main(),
    # cosa che rende sicuro un eventuale import del modulo (nessun codice Streamlit
    # top-level viene eseguito all'import).
    nomi_funzioni_top_level = [
        nodo.name for nodo in albero.body if isinstance(nodo, ast.FunctionDef)
    ]
    assert "main" in nomi_funzioni_top_level

    assert compileall.compile_file(str(percorso_app), quiet=1)


# ---------------------------------------------------------------------------
# Test di validazione CSV
# ---------------------------------------------------------------------------

def test_parse_esercizi_csv_valido():
    csv_testo = (
        "Nome,Spiegazione,Note,Ripetizioni,Recupero\n"
        "Squat,Scendi e risali,Attenzione alla schiena,3x12,90 SEC\n"
        "Plank,Mantieni la posizione,,1x60s,60 SEC\n"
    )
    esercizi = parse_esercizi_csv(io.StringIO(csv_testo))

    assert len(esercizi) == 2
    assert esercizi[0]["nome"] == "Squat"
    assert esercizi[0]["ripetizioni"] == "3x12"
    # Il valore NaN (colonna Note vuota nella seconda riga) deve diventare stringa vuota.
    assert esercizi[1]["note"] == ""


def test_parse_esercizi_csv_colonne_mancanti():
    csv_testo = "Nome,Spiegazione\nSquat,Scendi e risali\n"
    with pytest.raises(ValueError) as errore:
        parse_esercizi_csv(io.StringIO(csv_testo))

    messaggio = str(errore.value)
    assert "colonne" in messaggio.lower() or "mancanti" in messaggio.lower()


# ---------------------------------------------------------------------------
# Test di estrazione frame (richiede ffmpeg reale, nessuna rete)
# ---------------------------------------------------------------------------

def test_extract_frame_da_video_sintetico(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg non è installato: impossibile eseguire questo test.")

    video_path = tmp_path / "test.mp4"
    comando_generazione = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "testsrc=duration=5:size=320x240:rate=10",
        "-y",
        str(video_path),
    ]
    risultato_generazione = subprocess.run(
        comando_generazione, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
    )
    assert risultato_generazione.returncode == 0, risultato_generazione.stderr.decode(
        "utf-8", errors="ignore"
    )
    assert video_path.exists()

    output_path = tmp_path / "out.jpg"
    percorso_restituito = extract_frame(str(video_path), 2.0, str(output_path))

    assert percorso_restituito == str(output_path)
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    with open(output_path, "rb") as file_immagine:
        intestazione = file_immagine.read(2)
    assert intestazione == b"\xff\xd8"  # magic bytes JPEG


def test_extract_frame_fallisce_con_input_non_valido(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg non è installato: impossibile eseguire questo test.")

    output_path = tmp_path / "out.jpg"
    with pytest.raises(FrameExtractionError):
        extract_frame(str(tmp_path / "video_inesistente.mp4"), 0.0, str(output_path))


# ---------------------------------------------------------------------------
# Test di create_workout_document con servizi Google mockati
# ---------------------------------------------------------------------------

class _RisultatoEseguibile:
    """Wrapper minimale che imita l'oggetto restituito dalle chiamate googleapiclient
    prima di invocare .execute()."""

    def __init__(self, valore):
        self._valore = valore

    def execute(self):
        return self._valore


class FakeGoogleDocState:
    """
    Simula lo stato di un Google Doc, abbastanza fedele da supportare la
    sequenza di chiamate usata da create_workout_document: creazione,
    inserimento tabelle, popolamento celle, stile tabella, interruzioni
    di pagina. Non replica gli indici reali carattere per carattere: è
    una semplificazione sufficiente a rendere il test significativo dal
    punto di vista strutturale (numero di tabelle, page break, pageSize).
    """

    def __init__(self):
        self.doc_id = "fake_doc_id_123"
        self.next_index = 2
        self.content = [{"startIndex": 1, "endIndex": 2, "paragraph": {}}]
        self.tables_inserted = 0
        self.page_breaks_inserted = 0
        self.all_batch_requests = []  # una voce per ogni chiamata batchUpdate

    def snapshot(self):
        return {"documentId": self.doc_id, "body": {"content": list(self.content)}}

    def apply(self, requests):
        self.all_batch_requests.append(requests)
        for richiesta in requests:
            if "insertTable" in richiesta:
                self._insert_table()
            elif "insertPageBreak" in richiesta:
                self._insert_page_break()
            # Le altre richieste (insertText, updateTextStyle, insertInlineImage,
            # updateTableCellStyle, updateTableColumnProperties, updateDocumentStyle,
            # updateParagraphStyle) restano registrate in all_batch_requests per le
            # asserzioni ma non alterano ulteriormente questo stato semplificato.

    def _insert_table(self):
        start = self.next_index
        left_para_start = start + 3
        right_para_start = left_para_start + 5
        end = right_para_start + 5

        tabella = {
            "startIndex": start,
            "endIndex": end,
            "table": {
                "tableRows": [
                    {
                        "tableCells": [
                            {
                                "content": [
                                    {"startIndex": left_para_start, "endIndex": left_para_start + 1, "paragraph": {}}
                                ]
                            },
                            {
                                "content": [
                                    {"startIndex": right_para_start, "endIndex": right_para_start + 1, "paragraph": {}}
                                ]
                            },
                        ]
                    }
                ]
            },
        }
        self.content.append(tabella)
        self.next_index = end + 1
        self.content.append({"startIndex": end, "endIndex": self.next_index, "paragraph": {}})
        self.tables_inserted += 1

    def _insert_page_break(self):
        start = self.next_index - 1
        end = start + 2
        self.content[-1] = {"startIndex": start, "endIndex": end, "paragraph": {}}
        self.next_index = end
        self.page_breaks_inserted += 1


class FakeDocumentsResource:
    def __init__(self, stato):
        self.stato = stato

    def create(self, body):
        self.stato.title = body.get("title")
        return _RisultatoEseguibile({"documentId": self.stato.doc_id})

    def get(self, documentId):
        return _RisultatoEseguibile(self.stato.snapshot())

    def batchUpdate(self, documentId, body):
        self.stato.apply(body["requests"])
        return _RisultatoEseguibile({"documentId": documentId})


class FakeDocsService:
    def __init__(self, stato):
        self.stato = stato

    def documents(self):
        return FakeDocumentsResource(self.stato)


class FakeDriveState:
    def __init__(self):
        self.created_files = []
        self.deleted_files = []
        self._contatore = 0


class FakeFilesResource:
    def __init__(self, stato):
        self.stato = stato

    def create(self, body=None, media_body=None, fields=None):
        self.stato._contatore += 1
        file_id = f"file_{self.stato._contatore}"
        self.stato.created_files.append(file_id)
        return _RisultatoEseguibile({"id": file_id})

    def delete(self, fileId):
        self.stato.deleted_files.append(fileId)
        return _RisultatoEseguibile({})


class FakePermissionsResource:
    def create(self, fileId, body=None):
        return _RisultatoEseguibile({})


class FakeDriveService:
    def __init__(self, stato):
        self.stato = stato

    def files(self):
        return FakeFilesResource(self.stato)

    def permissions(self):
        return FakePermissionsResource()


def test_create_workout_document_con_servizi_mockati(tmp_path):
    immagine_start = tmp_path / "start.jpg"
    immagine_start.write_bytes(b"\xff\xd8\xff\xe0finto_jpeg_start")
    immagine_finish = tmp_path / "finish.jpg"
    immagine_finish.write_bytes(b"\xff\xd8\xff\xe0finto_jpeg_finish")

    esercizi = [
        {
            "nome": f"Esercizio {n + 1}",
            "spiegazione": "Spiegazione di prova per il test.",
            "note": "Nota di prova.",
            "ripetizioni": "3x10",
            "recupero": "60 SEC",
            "frame_start": str(immagine_start),
            "frame_finish": str(immagine_finish),
        }
        for n in range(4)
    ]

    stato_doc = FakeGoogleDocState()
    stato_drive = FakeDriveState()
    docs_service = FakeDocsService(stato_doc)
    drive_service = FakeDriveService(stato_drive)

    risultato = create_workout_document(
        esercizi, "Scheda di Test", docs_service=docs_service, drive_service=drive_service
    )

    assert risultato["document_id"] == stato_doc.doc_id
    assert risultato["url"] == f"https://docs.google.com/document/d/{stato_doc.doc_id}/edit"

    # Il primo batchUpdate deve contenere l'impostazione pageSize formato A4.
    primo_batch = stato_doc.all_batch_requests[0]
    trovato_page_size = False
    for richiesta in primo_batch:
        if "updateDocumentStyle" in richiesta:
            page_size = richiesta["updateDocumentStyle"]["documentStyle"]["pageSize"]
            assert abs(page_size["width"]["magnitude"] - 595.28) < 0.01
            assert abs(page_size["height"]["magnitude"] - 841.89) < 0.01
            trovato_page_size = True
    assert trovato_page_size, "Nessuna richiesta updateDocumentStyle con pageSize A4 trovata."

    # 4 esercizi -> 4 tabelle 1x2 inserite.
    assert stato_doc.tables_inserted == 4

    # Con 4 esercizi ci si aspetta almeno un'interruzione di pagina (dopo il 3°).
    assert stato_doc.page_breaks_inserted >= 1

    # 2 immagini per esercizio * 4 esercizi = 8 file caricati su Drive, e tutti
    # devono essere stati eliminati a fine generazione (best-effort cleanup).
    assert len(stato_drive.created_files) == 8
    assert sorted(stato_drive.deleted_files) == sorted(stato_drive.created_files)
