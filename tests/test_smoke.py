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
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from googleapiclient.errors import HttpError
from PIL import Image

# Rendiamo importabili i moduli del progetto (root della repo) indipendentemente
# da dove viene lanciato pytest.
RADICE_PROGETTO = Path(__file__).resolve().parent.parent
if str(RADICE_PROGETTO) not in sys.path:
    sys.path.insert(0, str(RADICE_PROGETTO))

from core import csv_utils, docs_helper as google_docs_helper, scheda_file, video_helper  # noqa: E402
from core.csv_utils import esercizi_csv_bytes, parse_esercizi_csv, scrivi_esercizi_csv, slugify  # noqa: E402
from core.docs_helper import create_workout_document, get_credentials, update_exercise_media  # noqa: E402
from core.video_helper import (  # noqa: E402
    FrameExtractionError,
    box_ritaglio,
    crop_frame,
    extract_frame,
    filtra_risultati_pertinenti,
    get_stream_info,
    importa_frame_da_immagine,
)
from core import platform  # noqa: E402
from core.platform import CredentialProviderError  # noqa: E402


# ---------------------------------------------------------------------------
# Test di import / validità sintattica dei moduli
# ---------------------------------------------------------------------------

def test_import_moduli_principali():
    """I moduli 'puri' del progetto devono essere importabili senza errori."""
    assert hasattr(video_helper, "search_youtube")
    assert hasattr(video_helper, "get_stream_url")
    assert hasattr(video_helper, "extract_frame")
    assert hasattr(video_helper, "extract_start_finish_frames")
    assert hasattr(video_helper, "filtra_risultati_pertinenti")
    assert hasattr(video_helper, "scegli_ed_estrai")
    assert hasattr(video_helper, "get_video_info")
    assert hasattr(video_helper, "box_ritaglio")
    assert hasattr(video_helper, "crop_frame")
    assert hasattr(google_docs_helper, "create_workout_document")
    assert hasattr(google_docs_helper, "update_exercise_media")
    assert hasattr(google_docs_helper, "get_credentials")
    assert hasattr(google_docs_helper, "get_credentials_manual_flow")
    assert hasattr(csv_utils, "parse_esercizi_csv")
    assert hasattr(csv_utils, "scrivi_esercizi_csv")
    assert hasattr(csv_utils, "esercizi_csv_bytes")
    assert hasattr(scheda_file, "carica_scheda")
    assert hasattr(scheda_file, "carica_scheda_da_file_like")
    assert hasattr(scheda_file, "salva_scheda")
    assert hasattr(scheda_file, "scheda_bytes")
    assert hasattr(scheda_file, "cartella_lavoro_per_bundle")
    assert hasattr(scheda_file, "cartella_frames")
    assert hasattr(scheda_file, "percorso_stato")
    assert hasattr(scheda_file, "SchedaFileError")


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


def test_salvataggio_non_riassegna_la_chiave_del_widget_titolo():
    """Il valore di un widget Streamlit non può essere scritto dopo la sua creazione."""
    percorso_app = RADICE_PROGETTO / "app.py"
    albero = ast.parse(percorso_app.read_text(encoding="utf-8"), filename=str(percorso_app))
    sidebar = next(nodo for nodo in albero.body if isinstance(nodo, ast.FunctionDef) and nodo.name == "_sidebar")

    assegnazioni_titolo = [
        nodo
        for nodo in ast.walk(sidebar)
        if isinstance(nodo, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and isinstance(target.value.value, ast.Name)
            and target.value.value.id == "st"
            and target.value.attr == "session_state"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "titolo_scheda"
            for target in (nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target])
        )
    ]
    assert len(assegnazioni_titolo) == 1


# ---------------------------------------------------------------------------
# Test del riordino della lista esercizi (logica pura di app.py)
# ---------------------------------------------------------------------------

def _lista_riordinata():
    """
    Importa la funzione di riordino di app.py. L'import e' sicuro (tutta la
    logica Streamlit e' dentro main()) ma resta locale al test, cosi' gli
    altri test non dipendono da streamlit installato.
    """
    app = pytest.importorskip("app")
    return app._lista_riordinata


def test_lista_riordinata_singolo_in_avanti():
    """Spostare un esercizio a una posizione piu' in basso lo porta esattamente
    a quel numero, facendo risalire di uno tutti quelli che scavalca."""
    riordina = _lista_riordinata()
    assert riordina(["a", "b", "c", "d", "e"], [1], 4) == ["a", "c", "d", "b", "e"]


def test_lista_riordinata_singolo_indietro():
    """Spostare un esercizio piu' in alto fa scendere di uno gli altri."""
    riordina = _lista_riordinata()
    assert riordina(["a", "b", "c", "d", "e"], [4], 2) == ["a", "e", "b", "c", "d"]


def test_lista_riordinata_blocco_mantiene_ordine_relativo():
    """Piu' esercizi selezionati si spostano in blocco, nell'ordine in cui erano."""
    riordina = _lista_riordinata()
    assert riordina(["a", "b", "c", "d", "e"], [0, 3], 3) == ["b", "c", "a", "d", "e"]


def test_lista_riordinata_posizione_fuori_scala_viene_limitata():
    """Una posizione oltre la fine (o sotto 1) finisce in fondo (o in testa)."""
    riordina = _lista_riordinata()
    assert riordina(["a", "b", "c"], [0], 99) == ["b", "c", "a"]
    assert riordina(["a", "b", "c"], [2], 0) == ["c", "a", "b"]


def test_lista_riordinata_non_muta_originale():
    """Il riordino ritorna una nuova lista: l'originale resta intatta."""
    riordina = _lista_riordinata()
    originale = ["a", "b", "c"]
    riordina(originale, [0], 3)
    assert originale == ["a", "b", "c"]


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


def test_parse_esercizi_csv_5_colonne_valori_opzionali_default():
    """Un CSV con le sole 5 colonne obbligatorie deve popolare comunque le chiavi
    opzionali del manifest, con i default retrocompatibili."""
    csv_testo = (
        "Nome,Spiegazione,Note,Ripetizioni,Recupero\n"
        "Squat,Scendi e risali,Attenzione alla schiena,3x12,90 SEC\n"
    )
    esercizi = parse_esercizi_csv(io.StringIO(csv_testo))
    esercizio = esercizi[0]

    assert esercizio["gruppo"] == ""
    assert esercizio["video_url"] == ""
    assert esercizio["ts_start"] is None
    assert esercizio["ts_finish"] is None
    assert esercizio["frame_start"] is None
    assert esercizio["frame_finish"] is None


def test_parse_esercizi_csv_11_colonne_valori_letti():
    csv_testo = (
        "Nome,Spiegazione,Note,Ripetizioni,Recupero,Gruppo,VideoURL,"
        "TimestampStart,TimestampFinish,FrameStartPath,FrameFinishPath\n"
        "Squat,Scendi e risali,Attenzione,3x12,90 SEC,Attivazione,"
        "https://youtu.be/abc,6,24.5,frames/squat_start.jpg,frames/squat_finish.jpg\n"
    )
    esercizi = parse_esercizi_csv(io.StringIO(csv_testo))
    esercizio = esercizi[0]

    assert esercizio["gruppo"] == "Attivazione"
    assert esercizio["video_url"] == "https://youtu.be/abc"
    assert esercizio["ts_start"] == 6.0
    assert isinstance(esercizio["ts_start"], float)
    assert esercizio["ts_finish"] == 24.5
    assert esercizio["frame_start"] == "frames/squat_start.jpg"
    assert esercizio["frame_finish"] == "frames/squat_finish.jpg"


def test_parse_esercizi_csv_timestamp_non_numerico():
    csv_testo = (
        "Nome,Spiegazione,Note,Ripetizioni,Recupero,TimestampStart\n"
        "Squat,Scendi e risali,Attenzione,3x12,90 SEC,non_numerico\n"
    )
    with pytest.raises(ValueError) as errore:
        parse_esercizi_csv(io.StringIO(csv_testo))

    assert "TimestampStart" in str(errore.value)


def test_scrivi_esercizi_csv_round_trip(tmp_path):
    """scrivi_esercizi_csv → parse_esercizi_csv deve restituire gli stessi valori."""
    esercizi = [
        {
            "nome": "Squat",
            "spiegazione": "Scendi e risali",
            "note": "Attenzione alla schiena",
            "ripetizioni": "3x12",
            "recupero": "90 SEC",
            "gruppo": "Attivazione",
            "video_url": "https://youtu.be/abc",
            "ts_start": 6.0,
            "ts_finish": 24.0,
            "frame_start": "frames/squat_start.jpg",
            "frame_finish": "frames/squat_finish.jpg",
        },
        {
            "nome": "Plank",
            "spiegazione": "Mantieni la posizione",
            "note": "",
            "ripetizioni": "1x60s",
            "recupero": "60 SEC",
            "gruppo": "",
            "video_url": "",
            "ts_start": None,
            "ts_finish": None,
            "frame_start": None,
            "frame_finish": None,
        },
    ]
    percorso = tmp_path / "scheda.csv"
    scrivi_esercizi_csv(esercizi, str(percorso))
    riletti = parse_esercizi_csv(str(percorso))

    assert riletti == esercizi


def test_esercizi_csv_bytes_round_trip():
    """esercizi_csv_bytes → parse_esercizi_csv deve restituire gli stessi valori
    ottenuti passando per un file su disco (stessa logica, buffer in memoria)."""
    esercizi = [
        {
            "nome": "Squat",
            "spiegazione": "Scendi e risali",
            "note": "Attenzione alla schiena",
            "ripetizioni": "3x12",
            "recupero": "90 SEC",
            "gruppo": "Attivazione",
            "video_url": "https://youtu.be/abc",
            "ts_start": 6.0,
            "ts_finish": 24.0,
            "frame_start": "frames/squat_start.jpg",
            "frame_finish": "frames/squat_finish.jpg",
        },
        {
            "nome": "Plank",
            "spiegazione": "Mantieni la posizione",
            "note": "",
            "ripetizioni": "1x60s",
            "recupero": "60 SEC",
            "gruppo": "",
            "video_url": "",
            "ts_start": None,
            "ts_finish": None,
            "frame_start": None,
            "frame_finish": None,
        },
    ]
    dati_csv = esercizi_csv_bytes(esercizi)
    assert isinstance(dati_csv, bytes)

    riletti = parse_esercizi_csv(io.BytesIO(dati_csv))
    assert riletti == esercizi


# ---------------------------------------------------------------------------
# Test del filtro di rilevanza dei video (video_helper.filtra_risultati_pertinenti)
# ---------------------------------------------------------------------------

def test_filtra_risultati_pertinenti_scarta_video_non_pertinente():
    """Caso reale di riferimento: 'Short Foot' agganciato a un video di boxe."""
    risultati = [
        {"title": "Anthony Joshua Boxing Workout", "duration": 300, "webpage_url": "https://x"},
    ]
    pertinenti, scartati = filtra_risultati_pertinenti("Short Foot Piede Corto", risultati)

    assert pertinenti == []
    assert len(scartati) == 1
    assert scartati[0]["video"] is risultati[0]
    assert scartati[0]["motivo"] != "durata"


def test_filtra_risultati_pertinenti_accetta_video_pertinente():
    risultati = [
        {
            "title": "Short Foot esercizio piede corto spiegazione",
            "duration": 180,
            "webpage_url": "https://y",
        },
    ]
    pertinenti, scartati = filtra_risultati_pertinenti("Short Foot Piede Corto", risultati)

    assert scartati == []
    assert len(pertinenti) == 1
    assert pertinenti[0] is risultati[0]


def test_filtra_risultati_pertinenti_scarta_per_durata():
    risultati = [
        {
            "title": "Short Foot esercizio piede corto spiegazione",
            "duration": 5000,
            "webpage_url": "https://z",
        },
    ]
    pertinenti, scartati = filtra_risultati_pertinenti("Short Foot Piede Corto", risultati)

    assert pertinenti == []
    assert len(scartati) == 1
    assert scartati[0]["motivo"] == "durata"


# ---------------------------------------------------------------------------
# Test di orchestrazione video_helper.scegli_ed_estrai
# ---------------------------------------------------------------------------

def test_scegli_ed_estrai_frame_gia_presenti_non_cerca(tmp_path, monkeypatch):
    percorso_start = tmp_path / "e_start.jpg"
    percorso_finish = tmp_path / "e_finish.jpg"
    percorso_start.write_bytes(b"\xff\xd8\xff\xe0start")
    percorso_finish.write_bytes(b"\xff\xd8\xff\xe0finish")

    def _search_che_fallisce_il_test(*args, **kwargs):
        raise AssertionError("search_youtube non deve essere chiamata se i frame esistono già.")

    monkeypatch.setattr(video_helper, "search_youtube", _search_che_fallisce_il_test)

    esercizio = {
        "nome": "Squat",
        "frame_start": str(percorso_start),
        "frame_finish": str(percorso_finish),
    }
    risultato = video_helper.scegli_ed_estrai(esercizio, logger=lambda messaggio: None)

    assert risultato is esercizio
    assert risultato["frame_start"] == str(percorso_start)
    assert risultato["frame_finish"] == str(percorso_finish)


def test_scegli_ed_estrai_video_url_forzato_usa_url_e_timestamp_del_manifest(tmp_path, monkeypatch):
    chiamate = {}

    def _estrai_fittizio(video_url, ts_start, ts_finish, exercise_name, output_dir="frames"):
        chiamate["video_url"] = video_url
        chiamate["ts_start"] = ts_start
        chiamate["ts_finish"] = ts_finish
        return (str(tmp_path / "s.jpg"), str(tmp_path / "f.jpg"))

    def _search_che_fallisce_il_test(*args, **kwargs):
        raise AssertionError("search_youtube non deve essere chiamata se VideoURL è forzato.")

    monkeypatch.setattr(video_helper, "extract_start_finish_frames", _estrai_fittizio)
    monkeypatch.setattr(video_helper, "search_youtube", _search_che_fallisce_il_test)

    esercizio = {
        "nome": "Squat",
        "video_url": "https://youtu.be/forzato",
        "ts_start": 5.0,
        "ts_finish": 20.0,
        "frame_start": None,
        "frame_finish": None,
    }
    risultato = video_helper.scegli_ed_estrai(esercizio, logger=lambda messaggio: None)

    assert chiamate["video_url"] == "https://youtu.be/forzato"
    assert chiamate["ts_start"] == 5.0
    assert chiamate["ts_finish"] == 20.0
    assert risultato["frame_start"] == str(tmp_path / "s.jpg")
    assert risultato["frame_finish"] == str(tmp_path / "f.jpg")


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


def test_extract_frame_inoltra_gli_header_yt_dlp_a_ffmpeg(tmp_path, monkeypatch):
    """Gli header associati allo stream evitano che YouTube rifiuti ffmpeg con 403."""
    output_path = tmp_path / "out.jpg"
    comandi = []

    def _run_fittizio(comando, **kwargs):
        comandi.append(comando)
        output_path.write_bytes(b"\xff\xd8frame")
        return subprocess.CompletedProcess(comando, returncode=0, stderr=b"")

    monkeypatch.setattr(video_helper.subprocess, "run", _run_fittizio)

    extract_frame(
        "https://googlevideo.example/stream",
        12.0,
        str(output_path),
        {"User-Agent": "yt-dlp-test", "Referer": "https://www.youtube.com/"},
    )

    comando = comandi[0]
    indice_header = comando.index("-headers")
    assert comando[indice_header + 1] == "User-Agent: yt-dlp-test\r\nReferer: https://www.youtube.com/\r\n"
    assert comando[indice_header + 2 : indice_header + 4] == ["-i", "https://googlevideo.example/stream"]


def test_extract_frame_usa_backend_iniettato(tmp_path):
    output_path = tmp_path / "out.jpg"

    class BackendFinto:
        def __init__(self):
            self.comandi = []

        def run(self, comando, *, timeout):
            self.comandi.append((comando, timeout))
            output_path.write_bytes(b"\xff\xd8frame")
            return subprocess.CompletedProcess(comando, returncode=0, stderr=b"")

    backend = BackendFinto()
    assert extract_frame("video.mp4", 3.0, str(output_path), ffmpeg_backend=backend) == str(output_path)
    assert backend.comandi[0][0][0] == "ffmpeg"
    assert backend.comandi[0][1] == 90


def test_get_credentials_usa_provider_iniettato(tmp_path):
    class ProviderFinto:
        def __init__(self):
            self.scopes = None

        def get_credentials(self, scopes):
            self.scopes = scopes
            return "credenziali-finte"

    provider = ProviderFinto()
    assert get_credentials(credential_provider=provider, base_dir=tmp_path) == "credenziali-finte"
    assert provider.scopes


def test_get_credentials_traduce_errore_del_provider():
    class ProviderFinto:
        def get_credentials(self, scopes):
            raise CredentialProviderError("credenziali mancanti")

    with pytest.raises(google_docs_helper.GoogleAuthError, match="credenziali mancanti"):
        get_credentials(credential_provider=ProviderFinto())


def test_get_stream_info_restituisce_gli_header_yt_dlp(monkeypatch):
    class _YoutubeDLFinto:
        def __init__(self, opzioni):
            self.opzioni = opzioni

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, video_url, download):
            return {
                "url": "https://googlevideo.example/stream",
                "vcodec": "h264",
                "http_headers": {"User-Agent": "formato-specifico"},
            }

    monkeypatch.setattr(video_helper.yt_dlp, "YoutubeDL", _YoutubeDLFinto)

    stream_url, headers = get_stream_info("https://www.youtube.com/watch?v=test")

    assert stream_url == "https://googlevideo.example/stream"
    assert headers == {"User-Agent": "formato-specifico"}


# ---------------------------------------------------------------------------
# Test di ritaglio frame (video_helper.box_ritaglio / crop_frame)
# ---------------------------------------------------------------------------

def test_box_ritaglio():
    """Verifica la formula su size (200, 100) con percentuali note."""
    box = box_ritaglio((200, 100), sinistra_pct=10, alto_pct=20, destra_pct=5, basso_pct=25)
    assert box == (20, 20, 190, 75)

    # Nessun ritaglio: il box coincide con l'intera immagine.
    assert box_ritaglio((200, 100)) == (0, 0, 200, 100)


def _crea_immagine_di_prova(percorso, size=(200, 100)):
    """Crea e salva un'immagine RGB di prova (tinta unita) per i test di ritaglio."""
    immagine = Image.new("RGB", size, color=(120, 30, 200))
    immagine.save(percorso, "JPEG")
    return percorso


def test_crop_frame_ritaglia_correttamente(tmp_path):
    percorso_originale = tmp_path / "frame.jpg"
    percorso_output = tmp_path / "frame_ritagliato.jpg"
    _crea_immagine_di_prova(percorso_originale)

    percorso_restituito = crop_frame(
        str(percorso_originale), 10, 10, 10, 10, output_path=str(percorso_output)
    )

    assert percorso_restituito == str(percorso_output)
    with Image.open(percorso_output) as immagine_ritagliata:
        assert immagine_ritagliata.size == (160, 80)

    with open(percorso_output, "rb") as file_immagine:
        intestazione = file_immagine.read(2)
    assert intestazione == b"\xff\xd8"  # magic bytes JPEG


def test_crop_frame_sovrascrive_di_default(tmp_path):
    percorso_originale = tmp_path / "frame.jpg"
    _crea_immagine_di_prova(percorso_originale)

    percorso_restituito = crop_frame(str(percorso_originale), 25, 0, 25, 0)

    assert percorso_restituito == str(percorso_originale)
    with Image.open(percorso_originale) as immagine_ritagliata:
        assert immagine_ritagliata.size == (100, 100)


def test_crop_frame_percentuali_non_valide(tmp_path):
    percorso_originale = tmp_path / "frame.jpg"
    _crea_immagine_di_prova(percorso_originale)

    with pytest.raises(ValueError):
        crop_frame(str(percorso_originale), sinistra_pct=50)

    with pytest.raises(ValueError):
        crop_frame(str(percorso_originale), sinistra_pct=45, destra_pct=45)


# ---------------------------------------------------------------------------
# Test dell'import di immagini manuali al posto dei frame estratti
# ---------------------------------------------------------------------------

def test_importa_frame_da_immagine_converte_e_nomina_come_i_frame(tmp_path):
    """
    Un PNG con trasparenza diventa un JPEG con lo stesso nome che avrebbe
    prodotto l'estrazione dal video, così il resto della pipeline non vede
    differenza tra un frame estratto e un'immagine dell'utente.
    """
    sorgente = tmp_path / "mia_foto.png"
    Image.new("RGBA", (120, 90), (255, 0, 0, 128)).save(sorgente)
    cartella_frames = tmp_path / "frames"

    percorso = importa_frame_da_immagine(
        str(sorgente), "Squat con bilanciere", "start", output_dir=str(cartella_frames)
    )

    assert percorso == str(cartella_frames / "squat_con_bilanciere_start.jpg")
    with Image.open(percorso) as immagine:
        assert immagine.mode == "RGB"  # trasparenza appiattita
        assert immagine.size == (120, 90)
    with open(percorso, "rb") as file_immagine:
        assert file_immagine.read(2) == b"\xff\xd8"  # magic bytes JPEG


def test_importa_frame_da_immagine_sostituisce_il_frame_esistente(tmp_path):
    """La nuova immagine prende il posto del frame già presente per l'esercizio."""
    cartella_frames = tmp_path / "frames"
    cartella_frames.mkdir()
    frame_estratto = cartella_frames / "panca_piana_finish.jpg"
    _crea_immagine_di_prova(frame_estratto)
    sorgente = tmp_path / "sostituta.png"
    Image.new("RGB", (64, 48), (0, 128, 0)).save(sorgente)

    percorso = importa_frame_da_immagine(
        str(sorgente), "Panca piana", "finish", output_dir=str(cartella_frames)
    )

    assert percorso == str(frame_estratto)
    with Image.open(percorso) as immagine:
        assert immagine.size == (64, 48)


def test_importa_frame_da_immagine_rimuove_il_backup_pre_ritaglio(tmp_path):
    """
    Il backup *_orig.jpg del frame precedente va eliminato: si riferisce a
    un'immagine che non c'è più e "Ripristina originale" la riporterebbe.
    """
    cartella_frames = tmp_path / "frames"
    cartella_frames.mkdir()
    _crea_immagine_di_prova(cartella_frames / "stacco_start.jpg")
    backup = cartella_frames / "stacco_start_orig.jpg"
    _crea_immagine_di_prova(backup)
    sorgente = tmp_path / "nuova.jpg"
    _crea_immagine_di_prova(sorgente)

    importa_frame_da_immagine(str(sorgente), "Stacco", "start", output_dir=str(cartella_frames))

    assert not backup.exists()


def test_importa_frame_da_immagine_suffisso_non_valido(tmp_path):
    sorgente = tmp_path / "foto.jpg"
    _crea_immagine_di_prova(sorgente)

    with pytest.raises(ValueError):
        importa_frame_da_immagine(str(sorgente), "Squat", "meta", output_dir=str(tmp_path))


def test_importa_frame_da_immagine_file_non_valido(tmp_path):
    """File inesistente o non immagine: errore chiaro, nessun file scritto."""
    with pytest.raises(FrameExtractionError):
        importa_frame_da_immagine(
            str(tmp_path / "non_esiste.jpg"), "Squat", "start", output_dir=str(tmp_path)
        )

    finto = tmp_path / "non_una_immagine.jpg"
    finto.write_text("questo e' testo, non un JPEG", encoding="utf-8")
    with pytest.raises(FrameExtractionError):
        importa_frame_da_immagine(str(finto), "Squat", "start", output_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Fake dei servizi Google Docs/Drive, condivisi dai test su create_workout_document
# e update_exercise_media.
# ---------------------------------------------------------------------------

class _RisultatoEseguibile:
    """Wrapper minimale che imita l'oggetto restituito dalle chiamate googleapiclient
    prima di invocare .execute()."""

    def __init__(self, valore):
        self._valore = valore

    def execute(self):
        return self._valore


class _RispostaHttpFinta:
    """Minimo indispensabile perché HttpError esponga .resp.status."""

    def __init__(self, status):
        self.status = status
        self.reason = {404: "Not Found", 403: "Forbidden"}.get(status, "Error")


def _http_error(status):
    """Costruisce un HttpError googleapiclient con il codice indicato."""
    messaggi = {
        404: "Requested entity was not found.",
        403: "The caller does not have permission",
    }
    contenuto = json.dumps(
        {"error": {"code": status, "message": messaggi.get(status, "errore")}}
    ).encode("utf-8")
    return HttpError(_RispostaHttpFinta(status), contenuto, uri="https://docs.googleapis.com/v1/documents/x")


class FakeGoogleDocState:
    """
    Simula lo stato di un Google Doc, abbastanza fedele da supportare la
    sequenza di chiamate usata da create_workout_document: creazione,
    inserimento tabelle, popolamento celle, stile tabella, named range,
    interruzioni di pagina. Non replica gli indici reali carattere per
    carattere: è una semplificazione sufficiente a rendere il test
    significativo dal punto di vista strutturale (numero di tabelle, page
    break, pageSize, intestazioni di gruppo, named range).
    """

    def __init__(self):
        self.doc_id = "fake_doc_id_123"
        self.next_index = 2
        self.content = [{"startIndex": 1, "endIndex": 2, "paragraph": {}}]
        self.tables_inserted = 0
        self.page_breaks_inserted = 0
        self.named_ranges_creati = 0
        self.create_calls = 0
        self.all_batch_requests = []  # una voce per ogni chiamata batchUpdate
        # doc_id -> codice HTTP con cui documents().get() deve fallire, per
        # simulare un documento cancellato (404) o non accessibile (403).
        self.errori_get = {}

    def snapshot(self):
        return {"documentId": self.doc_id, "body": {"content": list(self.content)}}

    def apply(self, requests):
        self.all_batch_requests.append(requests)
        replies = []
        for richiesta in requests:
            if "insertTable" in richiesta:
                self._insert_table()
                replies.append({})
            elif "insertPageBreak" in richiesta:
                self._insert_page_break()
                replies.append({})
            elif "createNamedRange" in richiesta:
                self.named_ranges_creati += 1
                replies.append(
                    {"createNamedRange": {"namedRangeId": f"nr_{self.named_ranges_creati}"}}
                )
            else:
                # Le altre richieste (insertText, updateTextStyle, insertInlineImage,
                # updateTableCellStyle, updateTableColumnProperties, updateDocumentStyle,
                # updateParagraphStyle) restano registrate in all_batch_requests per le
                # asserzioni ma non alterano ulteriormente questo stato semplificato.
                replies.append({})
        return replies

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
        self.stato.create_calls += 1
        self.stato.title = body.get("title")
        return _RisultatoEseguibile({"documentId": self.stato.doc_id})

    def get(self, documentId):
        codice = self.stato.errori_get.get(documentId)
        if codice:
            raise _http_error(codice)
        return _RisultatoEseguibile(self.stato.snapshot())

    def batchUpdate(self, documentId, body):
        replies = self.stato.apply(body["requests"])
        return _RisultatoEseguibile({"documentId": documentId, "replies": replies})


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


def _crea_esercizio_di_prova(nome, tmp_path, gruppo=""):
    """Costruisce un esercizio pronto (con frame fittizi già su disco) per i test."""
    immagine_start = tmp_path / f"{slugify(nome)}_start.jpg"
    immagine_finish = tmp_path / f"{slugify(nome)}_finish.jpg"
    if not immagine_start.exists():
        immagine_start.write_bytes(b"\xff\xd8\xff\xe0finto_jpeg_start")
    if not immagine_finish.exists():
        immagine_finish.write_bytes(b"\xff\xd8\xff\xe0finto_jpeg_finish")
    return {
        "nome": nome,
        "spiegazione": "Spiegazione di prova per il test.",
        "note": "Nota di prova.",
        "ripetizioni": "3x10",
        "recupero": "60 SEC",
        "gruppo": gruppo,
        "frame_start": str(immagine_start),
        "frame_finish": str(immagine_finish),
    }


# ---------------------------------------------------------------------------
# Test di create_workout_document con servizi Google mockati
# ---------------------------------------------------------------------------

def test_create_workout_document_con_servizi_mockati(tmp_path):
    esercizi = [_crea_esercizio_di_prova(f"Esercizio {n + 1}", tmp_path) for n in range(4)]

    stato_doc = FakeGoogleDocState()
    stato_drive = FakeDriveState()
    docs_service = FakeDocsService(stato_doc)
    drive_service = FakeDriveService(stato_drive)

    risultato = create_workout_document(
        esercizi, "Scheda di Test", docs_service=docs_service, drive_service=drive_service
    )

    assert risultato["document_id"] == stato_doc.doc_id
    assert risultato["url"] == f"https://docs.google.com/document/d/{stato_doc.doc_id}/edit"
    assert risultato["esercizi_inseriti"] == [e["nome"] for e in esercizi]

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

    # 4 esercizi -> 4 tabelle 1x2 inserite, e un named range per ciascuna.
    assert stato_doc.tables_inserted == 4
    assert stato_doc.named_ranges_creati == 4

    # Con 4 esercizi nello stesso gruppo implicito ci si aspetta almeno un'interruzione
    # di pagina (dopo il 3°).
    assert stato_doc.page_breaks_inserted >= 1

    # 2 immagini per esercizio * 4 esercizi = 8 file caricati su Drive, e tutti
    # devono essere stati eliminati a fine generazione (best-effort cleanup).
    assert len(stato_drive.created_files) == 8
    assert sorted(stato_drive.deleted_files) == sorted(stato_drive.created_files)


def test_create_workout_document_esercizi_omonimi_hanno_slug_distinti(tmp_path):
    """Due esercizi con lo stesso nome devono entrambi finire nel documento."""
    esercizi = [
        _crea_esercizio_di_prova("Squat", tmp_path),
        _crea_esercizio_di_prova("Squat", tmp_path),
    ]
    stato_doc = FakeGoogleDocState()
    stato_drive = FakeDriveState()
    percorso_stato = tmp_path / "scheda.state.json"

    risultato = create_workout_document(
        esercizi,
        "Scheda con omonimi",
        docs_service=FakeDocsService(stato_doc),
        drive_service=FakeDriveService(stato_drive),
        state_path=str(percorso_stato),
    )

    assert risultato["esercizi_inseriti"] == ["Squat", "Squat"]
    assert stato_doc.tables_inserted == 2
    stato_salvato = json.loads(percorso_stato.read_text(encoding="utf-8"))
    assert [esercizio["slug"] for esercizio in stato_salvato["esercizi"]] == ["squat", "squat_2"]


def test_create_workout_document_campi_vuoti_niente_range_vuoti(tmp_path):
    """
    Un esercizio con campi non compilati (note, spiegazione, ripetizioni,
    recupero) non deve produrre updateTextStyle con range vuoto: Google Docs
    risponderebbe 400 "The range should not be empty" facendo fallire tutto
    il batchUpdate, e quindi l'intera generazione del documento.
    """
    esercizio = _crea_esercizio_di_prova("Esercizio senza note", tmp_path)
    esercizio.update({"note": "", "spiegazione": "", "ripetizioni": "", "recupero": ""})

    stato_doc = FakeGoogleDocState()
    docs_service = FakeDocsService(stato_doc)
    drive_service = FakeDriveService(FakeDriveState())

    risultato = create_workout_document(
        [esercizio], "Scheda con campi vuoti",
        docs_service=docs_service, drive_service=drive_service,
    )

    assert risultato["esercizi_inseriti"] == ["Esercizio senza note"]

    range_vuoti = [
        richiesta
        for batch in stato_doc.all_batch_requests
        for richiesta in batch
        if "updateTextStyle" in richiesta
        and richiesta["updateTextStyle"]["range"]["startIndex"]
        >= richiesta["updateTextStyle"]["range"]["endIndex"]
    ]
    assert not range_vuoti, f"updateTextStyle con range vuoto: {range_vuoti}"


def test_richieste_cella_destra_offset_corretti_con_campi_vuoti():
    """
    Saltare i segmenti vuoti non deve spostare i range dei segmenti successivi:
    gli offset restano calcolati sul testo completo davvero inserito.
    """
    esercizio = {
        "nome": "SQUAT", "spiegazione": "", "note": "Schiena neutra.",
        "ripetizioni": "3x10", "recupero": "",
    }
    richieste = google_docs_helper._richieste_cella_destra(100, esercizio)

    testo_inserito = richieste[0]["insertText"]["text"]
    assert richieste[0]["insertText"]["location"]["index"] == 100

    for richiesta in richieste[1:]:
        intervallo = richiesta["updateTextStyle"]["range"]
        inizio, fine = intervallo["startIndex"], intervallo["endIndex"]
        assert inizio < fine, "range vuoto"
        # Ogni range deve ricadere dentro il testo effettivamente inserito.
        assert 100 <= inizio < 100 + len(testo_inserito)
        assert fine <= 100 + len(testo_inserito)

    # Il range del nome copre esattamente "SQUAT", quello delle note esattamente
    # il testo delle note: la mappa testo/stile non e' scivolata.
    def _porzione(richiesta):
        intervallo = richiesta["updateTextStyle"]["range"]
        return testo_inserito[intervallo["startIndex"] - 100 : intervallo["endIndex"] - 100]

    porzioni = [_porzione(r) for r in richieste[1:]]
    assert "SQUAT" in porzioni
    assert "Schiena neutra." in porzioni
    assert "3x10" in porzioni
    assert "" not in porzioni


def test_create_workout_document_gruppi_intestazioni_e_page_break(tmp_path):
    """4 esercizi in 2 gruppi (2+2): 4 tabelle, 2 intestazioni di gruppo, 1 page break
    al cambio di gruppo (nessun page break interno perché i gruppi hanno solo 2 esercizi)."""
    esercizi = [
        _crea_esercizio_di_prova("Plank", tmp_path, gruppo="Attivazione"),
        _crea_esercizio_di_prova("Bird Dog", tmp_path, gruppo="Attivazione"),
        _crea_esercizio_di_prova("Squat", tmp_path, gruppo="Rinforzo Muscolare"),
        _crea_esercizio_di_prova("Affondi", tmp_path, gruppo="Rinforzo Muscolare"),
    ]

    stato_doc = FakeGoogleDocState()
    stato_drive = FakeDriveState()
    docs_service = FakeDocsService(stato_doc)
    drive_service = FakeDriveService(stato_drive)

    risultato = create_workout_document(
        esercizi, "Scheda Gruppi", docs_service=docs_service, drive_service=drive_service
    )

    assert len(risultato["esercizi_inseriti"]) == 4
    assert stato_doc.tables_inserted == 4
    assert stato_doc.page_breaks_inserted == 1

    testi_inseriti = [
        richiesta["insertText"]["text"]
        for batch in stato_doc.all_batch_requests
        for richiesta in batch
        if "insertText" in richiesta
    ]
    assert "ATTIVAZIONE\n" in testi_inseriti
    assert "RINFORZO MUSCOLARE\n" in testi_inseriti


def test_create_workout_document_resumibilita(tmp_path):
    """Con uno stato precompilato (2 esercizi su 4 già presenti), la seconda run non
    chiama documents().create() e inserisce solo i 2 esercizi mancanti."""
    esercizi = [_crea_esercizio_di_prova(f"Esercizio {n + 1}", tmp_path) for n in range(4)]

    stato_doc = FakeGoogleDocState()
    stato_drive = FakeDriveState()
    docs_service = FakeDocsService(stato_doc)
    drive_service = FakeDriveService(stato_drive)

    percorso_stato = tmp_path / "scheda.state.json"
    stato_iniziale = {
        "doc_id": stato_doc.doc_id,
        "titolo": "Scheda Resumibile",
        "esercizi": [
            {
                "nome": "Esercizio 1",
                "slug": slugify("Esercizio 1"),
                "named_range_id": "nr_precedente_1",
                "gruppo": "",
            },
            {
                "nome": "Esercizio 2",
                "slug": slugify("Esercizio 2"),
                "named_range_id": "nr_precedente_2",
                "gruppo": "",
            },
        ],
    }
    percorso_stato.write_text(json.dumps(stato_iniziale), encoding="utf-8")

    risultato = create_workout_document(
        esercizi,
        "Scheda Resumibile",
        docs_service=docs_service,
        drive_service=drive_service,
        state_path=str(percorso_stato),
    )

    assert stato_doc.create_calls == 0
    assert stato_doc.tables_inserted == 2
    assert risultato["esercizi_inseriti"] == ["Esercizio 3", "Esercizio 4"]

    stato_finale = json.loads(percorso_stato.read_text(encoding="utf-8"))
    assert len(stato_finale["esercizi"]) == 4
    assert {voce["nome"] for voce in stato_finale["esercizi"]} == {
        "Esercizio 1", "Esercizio 2", "Esercizio 3", "Esercizio 4"
    }


def _stato_orfano(percorso_stato, doc_id_sparito, nomi_esercizi):
    """Scrive uno state.json che punta a un documento non più esistente."""
    percorso_stato.write_text(
        json.dumps(
            {
                "doc_id": doc_id_sparito,
                "titolo": "Scheda Orfana",
                "url": f"https://docs.google.com/document/d/{doc_id_sparito}/edit",
                "esercizi": [
                    {"nome": nome, "slug": slugify(nome), "named_range_id": f"nr_{n}", "gruppo": ""}
                    for n, nome in enumerate(nomi_esercizi)
                ],
            }
        ),
        encoding="utf-8",
    )


def test_create_workout_document_rigenera_se_documento_cancellato(tmp_path):
    """
    Se il documento indicato dallo stato è stato cancellato da Drive (404),
    la scheda viene rigenerata da zero in un documento nuovo con TUTTI gli
    esercizi: gli esercizi elencati nello stato orfano non vanno saltati,
    altrimenti il nuovo documento resterebbe vuoto.
    """
    esercizi = [_crea_esercizio_di_prova(f"Esercizio {n + 1}", tmp_path) for n in range(3)]

    stato_doc = FakeGoogleDocState()
    stato_doc.errori_get["doc_cancellato_999"] = 404
    docs_service = FakeDocsService(stato_doc)
    drive_service = FakeDriveService(FakeDriveState())

    percorso_stato = tmp_path / "scheda.state.json"
    _stato_orfano(percorso_stato, "doc_cancellato_999", ["Esercizio 1", "Esercizio 2"])

    risultato = create_workout_document(
        esercizi, "Scheda Orfana",
        docs_service=docs_service, drive_service=drive_service,
        state_path=str(percorso_stato),
    )

    assert stato_doc.create_calls == 1  # documento nuovo creato
    assert risultato["document_id"] == stato_doc.doc_id
    assert risultato["documento_rigenerato"] is True
    assert risultato["esercizi_inseriti"] == ["Esercizio 1", "Esercizio 2", "Esercizio 3"]
    assert stato_doc.tables_inserted == 3

    # Lo stato orfano è stato sostituito: nuovo doc_id e nessun residuo del vecchio.
    stato_finale = json.loads(percorso_stato.read_text(encoding="utf-8"))
    assert stato_finale["doc_id"] == stato_doc.doc_id
    assert len(stato_finale["esercizi"]) == 3
    assert all(voce["named_range_id"].startswith("nr_") for voce in stato_finale["esercizi"])


def test_create_workout_document_non_rigenera_se_errore_di_permessi(tmp_path):
    """
    Un 403 (o qualunque errore diverso da 404) non è un documento sparito: va
    segnalato, non deve far creare un doppione del documento.
    """
    esercizi = [_crea_esercizio_di_prova("Esercizio 1", tmp_path)]

    stato_doc = FakeGoogleDocState()
    stato_doc.errori_get["doc_senza_permessi"] = 403
    docs_service = FakeDocsService(stato_doc)
    drive_service = FakeDriveService(FakeDriveState())

    percorso_stato = tmp_path / "scheda.state.json"
    _stato_orfano(percorso_stato, "doc_senza_permessi", ["Esercizio 1"])

    with pytest.raises(google_docs_helper.GoogleDocsError):
        create_workout_document(
            esercizi, "Scheda Protetta",
            docs_service=docs_service, drive_service=drive_service,
            state_path=str(percorso_stato),
        )

    assert stato_doc.create_calls == 0
    # Lo stato non è stato toccato: il documento originale esiste ancora.
    stato_finale = json.loads(percorso_stato.read_text(encoding="utf-8"))
    assert stato_finale["doc_id"] == "doc_senza_permessi"


def test_create_workout_document_senza_stato_non_rigenera(tmp_path):
    """Senza state_path il flag documento_rigenerato resta False (nessuna ripresa)."""
    esercizi = [_crea_esercizio_di_prova("Esercizio 1", tmp_path)]
    stato_doc = FakeGoogleDocState()

    risultato = create_workout_document(
        esercizi, "Scheda Semplice",
        docs_service=FakeDocsService(stato_doc),
        drive_service=FakeDriveService(FakeDriveState()),
    )

    assert risultato["documento_rigenerato"] is False
    assert stato_doc.create_calls == 1


# ---------------------------------------------------------------------------
# Test di update_exercise_media
# ---------------------------------------------------------------------------

class FakeDocumentsResourceUpdateMedia:
    """
    Fake minimale per update_exercise_media: un solo documento statico con un
    named range 'esercizio_<slug>' che punta a una tabella con 2
    inlineObjectElement nella prima cella. Registra le richieste dei
    batchUpdate per le asserzioni.
    """

    def __init__(self, documento):
        self.documento = documento
        self.richieste_registrate = []

    def get(self, documentId):
        return _RisultatoEseguibile(self.documento)

    def batchUpdate(self, documentId, body):
        self.richieste_registrate.extend(body["requests"])
        return _RisultatoEseguibile({"documentId": documentId, "replies": [{} for _ in body["requests"]]})


class FakeDocsServiceUpdateMedia:
    def __init__(self, documento):
        self.risorsa = FakeDocumentsResourceUpdateMedia(documento)

    def documents(self):
        return self.risorsa


def test_update_exercise_media_sostituisce_solo_le_due_immagini(tmp_path, monkeypatch):
    slug = slugify("Squat")
    table_start, table_end = 50, 80
    left_start, left_end = table_start + 3, table_start + 6

    documento_fittizio = {
        "documentId": "doc_esistente",
        "namedRanges": {
            f"esercizio_{slug}": {
                "namedRanges": [
                    {"namedRangeId": "nr_1", "ranges": [{"startIndex": table_start, "endIndex": table_end}]}
                ]
            }
        },
        "body": {
            "content": [
                {"startIndex": 1, "endIndex": table_start, "paragraph": {}},
                {
                    "startIndex": table_start,
                    "endIndex": table_end,
                    "table": {
                        "tableRows": [
                            {
                                "tableCells": [
                                    {
                                        "content": [
                                            {
                                                "startIndex": left_start,
                                                "endIndex": left_start + 1,
                                                "paragraph": {
                                                    "elements": [
                                                        {
                                                            "startIndex": left_start,
                                                            "endIndex": left_start + 1,
                                                            "inlineObjectElement": {"inlineObjectId": "obj_start"},
                                                        }
                                                    ]
                                                },
                                            },
                                            {
                                                "startIndex": left_start + 1,
                                                "endIndex": left_end,
                                                "paragraph": {
                                                    "elements": [
                                                        {
                                                            "startIndex": left_start + 1,
                                                            "endIndex": left_end,
                                                            "inlineObjectElement": {"inlineObjectId": "obj_finish"},
                                                        }
                                                    ]
                                                },
                                            },
                                        ]
                                    },
                                    {"content": [{"startIndex": left_end, "endIndex": left_end + 1, "paragraph": {}}]},
                                ]
                            }
                        ]
                    },
                },
            ]
        },
    }

    docs_service = FakeDocsServiceUpdateMedia(documento_fittizio)
    stato_drive = FakeDriveState()
    drive_service = FakeDriveService(stato_drive)

    percorso_start_nuovo = tmp_path / "nuovo_start.jpg"
    percorso_finish_nuovo = tmp_path / "nuovo_finish.jpg"
    percorso_start_nuovo.write_bytes(b"\xff\xd8\xff\xe0nuovo_start")
    percorso_finish_nuovo.write_bytes(b"\xff\xd8\xff\xe0nuovo_finish")

    def _estrai_fittizio(video_url, ts_start, ts_finish, exercise_name, output_dir="frames"):
        return (str(percorso_start_nuovo), str(percorso_finish_nuovo))

    monkeypatch.setattr(video_helper, "extract_start_finish_frames", _estrai_fittizio)

    percorso_stato = tmp_path / "scheda.state.json"
    stato = {
        "doc_id": "doc_esistente",
        "titolo": "Scheda di Test",
        "esercizi": [{"nome": "Squat", "slug": slug, "named_range_id": "nr_1", "gruppo": ""}],
    }
    percorso_stato.write_text(json.dumps(stato), encoding="utf-8")

    risultato = update_exercise_media(
        "doc_esistente",
        "Squat",
        video_url="https://youtu.be/nuovo",
        ts_start=3.0,
        ts_finish=9.0,
        state_path=str(percorso_stato),
        docs_service=docs_service,
        drive_service=drive_service,
    )

    assert risultato == {
        "document_id": "doc_esistente",
        "esercizio": "Squat",
        "frame_start": str(percorso_start_nuovo),
        "frame_finish": str(percorso_finish_nuovo),
    }

    richieste = docs_service.risorsa.richieste_registrate
    richieste_delete = [r for r in richieste if "deleteContentRange" in r]
    richieste_insert_image = [r for r in richieste if "insertInlineImage" in r]
    richieste_insert_table = [r for r in richieste if "insertTable" in r]

    assert len(richieste_delete) == 2
    assert len(richieste_insert_image) == 2
    assert len(richieste_insert_table) == 0


# ---------------------------------------------------------------------------
# Test di get_credentials_manual_flow (OAuth headless)
# ---------------------------------------------------------------------------

class _FakeInstalledAppFlow:
    """Sostituto minimale di InstalledAppFlow: non richiede un client secrets valido."""

    def __init__(self):
        self.redirect_uri = None

    @classmethod
    def from_client_secrets_file(cls, client_secrets_file, scopes):
        return cls()

    def authorization_url(self, **kwargs):
        return "https://accounts.google.com/o/oauth2/v2/auth?fake=1", "stato_fittizio"


def test_get_credentials_manual_flow_senza_credentials_json(tmp_path, monkeypatch):
    with pytest.raises(google_docs_helper.GoogleAuthError):
        google_docs_helper.get_credentials_manual_flow(base_dir=tmp_path)


def test_get_credentials_manual_flow_restituisce_url_autorizzazione(tmp_path, monkeypatch):
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(platform, "InstalledAppFlow", _FakeInstalledAppFlow)

    with pytest.raises(google_docs_helper.GoogleAuthError) as errore:
        google_docs_helper.get_credentials_manual_flow(base_dir=tmp_path)

    assert "https://" in str(errore.value)
