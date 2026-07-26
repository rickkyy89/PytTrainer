"""
Test del bridge Python<->Kotlin per Android (android/app/src/main/python/android_bridge.py).

Il file vive fuori da tests/ (dentro android/app/src/main/python/), quindi va
reso importabile a mano come i moduli di radice. Non richiede rete né
credenziali Google reali: tutte le funzioni dei moduli condivisi che
parlerebbero con l'esterno (YouTube, Google Docs/Drive) sono mockate.

Copre in particolare: l'envelope JSON di successo, l'envelope di errore con
il codice giusto per ciascuna eccezione nota (VIDEO_SEARCH, FRAME, AUTH,
DOCS, SCHEDA, VALORE, IGNOTO) e la convenzione di percorso_frame().
"""

import json
import sys
from pathlib import Path

import pytest

RADICE_PROGETTO = Path(__file__).resolve().parent.parent
if str(RADICE_PROGETTO) not in sys.path:
    sys.path.insert(0, str(RADICE_PROGETTO))

CARTELLA_BRIDGE = RADICE_PROGETTO / "android" / "app" / "src" / "main" / "python"
if str(CARTELLA_BRIDGE) not in sys.path:
    sys.path.insert(0, str(CARTELLA_BRIDGE))

import google_docs_helper  # noqa: E402
import scheda_file  # noqa: E402
import video_helper  # noqa: E402
from google_docs_helper import GoogleAuthError, GoogleDocsError  # noqa: E402
from scheda_file import SchedaFileError  # noqa: E402
from video_helper import FrameExtractionError, VideoSearchError  # noqa: E402

import android_bridge  # noqa: E402


@pytest.fixture(autouse=True)
def _ripristina_backend_frame_ffmpeg():
    """Come in test_smoke.py: evita che un test contamini _BACKEND_FRAME per i successivi."""
    yield
    video_helper.imposta_backend_frame(None)


def _decodifica(risposta_grezza: str) -> dict:
    """Le funzioni del bridge restituiscono sempre una stringa JSON: la decodifichiamo per asserire."""
    assert isinstance(risposta_grezza, str)
    return json.loads(risposta_grezza)


# ---------------------------------------------------------------------------
# Envelope di successo
# ---------------------------------------------------------------------------


def test_versione_python_restituisce_envelope_ok():
    risposta = _decodifica(android_bridge.versione_python())
    assert risposta["ok"] is True
    assert isinstance(risposta["dati"], str)
    assert risposta["dati"].startswith(sys.version.split()[0])


def test_percorso_frame_rispetta_convenzione_slug(tmp_path):
    cartella_lavoro = str(tmp_path / "mia_scheda.scheda.work")

    risposta_start = _decodifica(
        android_bridge.percorso_frame(cartella_lavoro, "Squat a Corpo Libero!", "start")
    )
    risposta_finish = _decodifica(
        android_bridge.percorso_frame(cartella_lavoro, "Squat a Corpo Libero!", "finish")
    )

    assert risposta_start["ok"] is True
    assert risposta_finish["ok"] is True

    dir_frames = scheda_file.cartella_frames(cartella_lavoro)
    assert risposta_start["dati"] == str(Path(dir_frames) / "squat_a_corpo_libero_start.jpg")
    assert risposta_finish["dati"] == str(Path(dir_frames) / "squat_a_corpo_libero_finish.jpg")


def test_cerca_video_restituisce_pertinenti_e_scartati(monkeypatch):
    risultati_fittizi = [
        {"id": "abc", "title": "Squat esecuzione corretta", "duration": 120, "webpage_url": "https://y/1"},
        {"id": "def", "title": "Ricetta della torta", "duration": 300, "webpage_url": "https://y/2"},
    ]
    monkeypatch.setattr(video_helper, "search_youtube", lambda query, max_results=3: risultati_fittizi)

    risposta = _decodifica(android_bridge.cerca_video("Squat"))

    assert risposta["ok"] is True
    assert len(risposta["dati"]["pertinenti"]) == 1
    assert risposta["dati"]["pertinenti"][0]["id"] == "abc"
    assert len(risposta["dati"]["scartati"]) == 1
    assert risposta["dati"]["scartati"][0]["video"]["id"] == "def"
    assert "motivo" in risposta["dati"]["scartati"][0]


def test_box_ritaglio_json_ok():
    risposta = _decodifica(android_bridge.box_ritaglio_json(1000, 500, 10, 10, 10, 10))
    assert risposta["ok"] is True
    assert risposta["dati"] == [100, 50, 900, 450]


def test_registra_backend_frame_delega_a_oggetto_kotlin_fittizio(tmp_path):
    """
    Simula l'oggetto Kotlin EstrattoreFrameNativo: un semplice oggetto Python
    con un metodo estrai(streamUrl, timestampSecondi, percorsoOutput) è
    sufficiente per verificare che il wrapper del bridge lo richiami con la
    firma corretta e che imposta_backend_frame() lo registri per davvero.
    """

    class _EstrattoreFittizio:
        def __init__(self):
            self.chiamate = []

        def estrai(self, stream_url, timestamp_secondi, percorso_output):
            self.chiamate.append((stream_url, timestamp_secondi, percorso_output))
            Path(percorso_output).write_bytes(b"\xff\xd8\xff finto jpeg")
            return percorso_output

    estrattore = _EstrattoreFittizio()
    risposta = _decodifica(android_bridge.registra_backend_frame(estrattore))
    assert risposta["ok"] is True
    assert video_helper.backend_frame_attivo() is not None

    output_path = str(tmp_path / "frame.jpg")
    percorso_restituito = video_helper.extract_frame("https://stream.fittizio", 12.5, output_path)

    assert percorso_restituito == output_path
    assert estrattore.chiamate == [("https://stream.fittizio", 12.5, output_path)]
    assert Path(output_path).exists()


# ---------------------------------------------------------------------------
# Envelope di errore: un test per ciascun codice
# ---------------------------------------------------------------------------


def test_errore_video_search(monkeypatch):
    def _cerca_che_fallisce(query, max_results=3):
        raise VideoSearchError("YouTube irraggiungibile in questo test.")

    monkeypatch.setattr(video_helper, "search_youtube", _cerca_che_fallisce)

    risposta = _decodifica(android_bridge.cerca_video("Squat"))

    assert risposta["ok"] is False
    assert risposta["codice"] == "VIDEO_SEARCH"
    assert "YouTube irraggiungibile" in risposta["messaggio"]


def test_errore_frame(monkeypatch, tmp_path):
    def _crop_che_fallisce(*args, **kwargs):
        raise FrameExtractionError("Backend nativo fallito in questo test.")

    monkeypatch.setattr(video_helper, "crop_frame", _crop_che_fallisce)

    # Il frame deve esistere davvero: ritaglia() ne salva una copia di backup
    # prima di ritagliare, quindi su un percorso inesistente si fermerebbe
    # prima di arrivare a crop_frame (ed è quel che verifica il test qui sotto).
    percorso_frame = tmp_path / "frame.jpg"
    percorso_frame.write_bytes(b"contenuto finto")
    risposta = _decodifica(android_bridge.ritaglia(str(percorso_frame), 5, 5, 5, 5))

    assert risposta["ok"] is False
    assert risposta["codice"] == "FRAME"
    assert "Backend nativo fallito" in risposta["messaggio"]


def test_errore_auth(monkeypatch):
    def _crea_documento_che_fallisce(*args, **kwargs):
        raise GoogleAuthError("Token di accesso scaduto in questo test.")

    monkeypatch.setattr(android_bridge, "_servizi_google_da_token", lambda access_token: (None, None))
    monkeypatch.setattr(google_docs_helper, "create_workout_document", _crea_documento_che_fallisce)

    risposta = _decodifica(android_bridge.genera_documento("[]", "Titolo", "token-finto"))

    assert risposta["ok"] is False
    assert risposta["codice"] == "AUTH"
    assert "Token di accesso scaduto" in risposta["messaggio"]


def test_errore_docs(monkeypatch):
    def _crea_documento_che_fallisce(*args, **kwargs):
        raise GoogleDocsError("Errore API Docs in questo test.")

    monkeypatch.setattr(android_bridge, "_servizi_google_da_token", lambda access_token: (None, None))
    monkeypatch.setattr(google_docs_helper, "create_workout_document", _crea_documento_che_fallisce)

    risposta = _decodifica(android_bridge.genera_documento("[]", "Titolo", "token-finto"))

    assert risposta["ok"] is False
    assert risposta["codice"] == "DOCS"
    assert "Errore API Docs" in risposta["messaggio"]


def test_errore_scheda(monkeypatch):
    def _carica_che_fallisce(percorso_bundle, cartella_lavoro=None):
        raise SchedaFileError("Bundle corrotto in questo test.")

    monkeypatch.setattr(scheda_file, "carica_scheda", _carica_che_fallisce)

    risposta = _decodifica(android_bridge.carica("mia_scheda.scheda"))

    assert risposta["ok"] is False
    assert risposta["codice"] == "SCHEDA"
    assert "Bundle corrotto" in risposta["messaggio"]


def test_errore_valore_tipo_frame_non_valido():
    risposta = _decodifica(android_bridge.percorso_frame("/tmp/lavoro", "Squat", "laterale"))

    assert risposta["ok"] is False
    assert risposta["codice"] == "VALORE"
    assert "laterale" in risposta["messaggio"]


def test_errore_ignoto(monkeypatch):
    def _importa_che_esplode(percorso):
        raise RuntimeError("Errore imprevisto in questo test.")

    monkeypatch.setattr(android_bridge.csv_utils, "parse_esercizi_csv", _importa_che_esplode)

    risposta = _decodifica(android_bridge.importa_csv("qualsiasi.csv"))

    assert risposta["ok"] is False
    assert risposta["codice"] == "IGNOTO"
    assert "Errore imprevisto" in risposta["messaggio"]


def test_ritaglia_backup_e_ripristino(tmp_path):
    """
    Il ritaglio dal telefono deve comportarsi come quello dell'app Streamlit:
    salvare una sola volta l'originale accanto al frame (convenzione
    scheda_file.percorso_backup_frame) e poter tornare indietro.
    """
    from PIL import Image

    percorso = str(tmp_path / "esercizio_start.jpg")
    Image.new("RGB", (200, 100), "red").save(percorso)

    assert _decodifica(android_bridge.ha_backup_originale(percorso))["dati"] is False

    senza_backup = _decodifica(android_bridge.ripristina_originale(percorso))
    assert senza_backup["ok"] is False
    assert senza_backup["codice"] == "VALORE"

    assert _decodifica(android_bridge.ritaglia(percorso, 10, 20, 5, 25))["ok"] is True
    with Image.open(percorso) as ritagliata:
        assert ritagliata.size == (170, 55)
    assert _decodifica(android_bridge.ha_backup_originale(percorso))["dati"] is True

    # Un secondo ritaglio non deve sovrascrivere il backup: si deve poter
    # tornare all'immagine di partenza, non a quella già ritagliata una volta.
    assert _decodifica(android_bridge.ritaglia(percorso, 10, 10, 10, 10))["ok"] is True
    assert _decodifica(android_bridge.ripristina_originale(percorso))["ok"] is True
    with Image.open(percorso) as ripristinata:
        assert ripristinata.size == (200, 100)


def test_ritaglia_frame_inesistente(tmp_path):
    risposta = _decodifica(android_bridge.ritaglia(str(tmp_path / "assente.jpg"), 5, 5, 5, 5))

    assert risposta["ok"] is False
    assert risposta["codice"] == "VALORE"
    assert "non esiste" in risposta["messaggio"]


def test_ritaglia_e_ripristina_senza_poter_cambiare_i_metadati(tmp_path, monkeypatch):
    """
    Regressione osservata sul device: sullo storage privato di un'app Android
    os.chmod() sulla destinazione di una copia fallisce con EPERM, anche se la
    cartella è dell'app stessa. shutil.copy2() lo chiama sempre (copia anche
    permessi e timestamp), quindi il backup finiva sul disco integro ma
    l'eccezione arrivava prima del ritaglio, che non veniva mai eseguito.

    Qui os.chmod e os.utime sono resi indisponibili per simulare quel vincolo:
    ritaglio e ripristino devono funzionare lo stesso, perché di un backup
    conta il contenuto, non i metadati.
    """
    import os as modulo_os

    from PIL import Image

    def _vietato(*_argomenti, **_parametri):
        raise PermissionError(13, "Permission denied")

    percorso = str(tmp_path / "esercizio_start.jpg")
    Image.new("RGB", (200, 100), "blue").save(percorso)

    monkeypatch.setattr(modulo_os, "chmod", _vietato)
    monkeypatch.setattr(modulo_os, "utime", _vietato)

    ritaglio = _decodifica(android_bridge.ritaglia(percorso, 10, 20, 5, 25))
    assert ritaglio["ok"] is True, ritaglio
    with Image.open(percorso) as ritagliata:
        assert ritagliata.size == (170, 55)

    ripristino = _decodifica(android_bridge.ripristina_originale(percorso))
    assert ripristino["ok"] is True, ripristino
    with Image.open(percorso) as ripristinata:
        assert ripristinata.size == (200, 100)
