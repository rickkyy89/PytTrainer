"""
Bridge Python <-> Kotlin per l'app Android (via Chaquopy).

Unico file Python specifico di Android: tutto il resto della logica vive nei
4 moduli condivisi con il progetto desktop (video_helper, scheda_file,
csv_utils, google_docs_helper), copiati qui in fase di build dal task Gradle
"copiaModuliPython" (vedi app/build.gradle.kts) e mai duplicati in git.

Regola ferrea di questo file: NESSUN oggetto Python complesso attraversa il
confine Kotlin<->Python. Ogni funzione pubblica riceve solo stringhe/numeri
(più, per registra_backend_frame, un oggetto Kotlin su cui invocare un solo
metodo) e restituisce sempre una stringa JSON con l'envelope:

    {"ok": true,  "dati": <qualsiasi cosa serializzabile>}
    {"ok": false, "codice": "<CODICE>", "messaggio": "<testo italiano>"}

e non solleva MAI un'eccezione verso Kotlin: il decoratore @risposta_json
intercetta ogni eccezione nota dei moduli condivisi (e, in ultima istanza,
qualsiasi altra) e la traduce nell'envelope di errore. Passare da un'eccezione
Python non gestita al lato Kotlin attraverso Chaquopy sarebbe scomodo da
intercettare correttamente e fragile tra versioni: l'envelope JSON è un
confine esplicito e stabile.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import sys

import csv_utils
import google_docs_helper
import scheda_file
import video_helper
from google.oauth2.credentials import Credentials
from google_docs_helper import GoogleAuthError, GoogleDocsError
from googleapiclient.discovery import build
from scheda_file import SchedaFileError
from video_helper import FrameExtractionError, VideoSearchError

# Formato yt-dlp per lo stream risolto lato Android: privilegia i formati
# muxati progressivi (video+audio in un solo file) fino a 720p, perché sia
# ExoPlayer (anteprima video) sia MediaMetadataRetriever (estrazione frame,
# vedi EstrattoreFrameNativo.kt) li gestiscono senza dover demuxare/allineare
# tracce separate. Fallback progressivo fino al "prendi quel che c'è".
FORMATO_ANDROID = (
    "best[ext=mp4][acodec!=none][vcodec!=none][height<=720]/"
    "best[ext=mp4][height<=720]/best[height<=720]/best"
)


def _errore_json(codice: str, errore: Exception) -> str:
    return json.dumps({"ok": False, "codice": codice, "messaggio": str(errore)}, ensure_ascii=False)


def risposta_json(funzione):
    """
    Decoratore che incapsula una funzione del bridge nell'envelope JSON
    ok/errore descritto nel docstring del modulo. L'ordine dei blocchi
    except va dal più specifico al più generico: le eccezioni dei moduli
    condivisi sono sottoclassi dirette di Exception (non derivano l'una
    dall'altra), quindi l'ordine tra loro non cambia il comportamento, ma è
    comunque quello della tabella dei codici concordata.
    """

    @functools.wraps(funzione)
    def wrapper(*args, **kwargs):
        try:
            dati = funzione(*args, **kwargs)
            return json.dumps({"ok": True, "dati": dati}, ensure_ascii=False)
        except VideoSearchError as errore:
            return _errore_json("VIDEO_SEARCH", errore)
        except FrameExtractionError as errore:
            return _errore_json("FRAME", errore)
        except GoogleAuthError as errore:
            return _errore_json("AUTH", errore)
        except GoogleDocsError as errore:
            return _errore_json("DOCS", errore)
        except SchedaFileError as errore:
            return _errore_json("SCHEDA", errore)
        except ValueError as errore:
            return _errore_json("VALORE", errore)
        except Exception as errore:  # noqa: BLE001 - confine Kotlin: mai propagare.
            return _errore_json("IGNOTO", errore)

    return wrapper


def _servizi_google_da_token(access_token: str):
    """
    Costruisce i servizi Docs/Drive a partire da un access token OAuth già
    ottenuto lato Kotlin (via AppAuth): è così che si aggira l'OAuth "da
    desktop" di get_credentials() (che aprirebbe un browser locale e non ha
    senso su Android). Le credenziali sono costruite col solo access token,
    senza refresh token: il refresh, se serve, è responsabilità del lato
    Kotlin (AppAuth), non di questo bridge.
    """
    credenziali = Credentials(token=access_token)
    docs_service = build("docs", "v1", credentials=credenziali)
    drive_service = build("drive", "v3", credentials=credenziali)
    return docs_service, drive_service


# --------------------------------------------------------------------------
# Scheda (.scheda) e CSV
# --------------------------------------------------------------------------


@risposta_json
def carica(percorso_bundle: str, cartella_lavoro: str = "") -> dict:
    """Apre un .scheda; cartella_lavoro vuota = default deterministico di scheda_file."""
    esercizi, cartella = scheda_file.carica_scheda(percorso_bundle, cartella_lavoro or None)
    return {"esercizi": esercizi, "cartella_lavoro": cartella}


@risposta_json
def salva(json_esercizi: str, percorso_bundle: str, state_path: str = "") -> None:
    """Ricompatta il .scheda; state_path vuoto = nessuno stato incluso nel bundle."""
    esercizi = json.loads(json_esercizi)
    scheda_file.salva_scheda(esercizi, percorso_bundle, state_path or None)
    return None


@risposta_json
def importa_csv(percorso: str) -> list:
    """Legge un CSV manifest nudo (input di partenza, non l'artefatto persistente)."""
    return csv_utils.parse_esercizi_csv(percorso)


@risposta_json
def esporta_csv(json_esercizi: str, percorso: str) -> None:
    """Scrive un CSV manifest completo (11 colonne) a partire dagli esercizi correnti."""
    esercizi = json.loads(json_esercizi)
    csv_utils.scrivi_esercizi_csv(esercizi, percorso)
    return None


@risposta_json
def cartella_frames(cartella_lavoro: str) -> str:
    return scheda_file.cartella_frames(cartella_lavoro)


@risposta_json
def percorso_stato(cartella_lavoro: str) -> str:
    return scheda_file.percorso_stato(cartella_lavoro)


@risposta_json
def cartella_lavoro_per_bundle(percorso: str) -> str:
    return scheda_file.cartella_lavoro_per_bundle(percorso)


@risposta_json
def percorso_frame(cartella_lavoro: str, nome_esercizio: str, tipo: str) -> str:
    """
    Percorso convenzionale <frames>/<slug>_<tipo>.jpg. Esiste perché Kotlin
    non deve mai ricalcolare autonomamente lo slug: la slugificazione
    canonica (csv_utils.slugify) resta l'unica fonte di verità.
    """
    if tipo not in ("start", "finish"):
        raise ValueError(f"Tipo di frame non valido: '{tipo}'. Deve essere 'start' o 'finish'.")
    slug = csv_utils.slugify(nome_esercizio)
    return os.path.join(scheda_file.cartella_frames(cartella_lavoro), f"{slug}_{tipo}.jpg")


# --------------------------------------------------------------------------
# Ricerca video / estrazione frame
# --------------------------------------------------------------------------


@risposta_json
def cerca_video(nome: str, max_results: int = 3) -> dict:
    risultati = video_helper.search_youtube(nome, max_results)
    pertinenti, scartati = video_helper.filtra_risultati_pertinenti(nome, risultati)
    return {"pertinenti": pertinenti, "scartati": scartati}


@risposta_json
def info_video(url: str) -> dict:
    return video_helper.get_video_info(url)


@risposta_json
def stream_url(url: str) -> str:
    return video_helper.get_stream_url(url, formato=FORMATO_ANDROID)


@risposta_json
def auto_estrai(json_esercizio: str, output_dir: str) -> dict:
    """
    Orchestrazione completa scelta-video + estrazione frame per un
    esercizio. Il logger di scegli_ed_estrai() normalmente stampa: qui invece
    accumuliamo le righe in una lista, che va mostrata all'utente (scelte e
    scarti, con motivo, per ogni esercizio).
    """
    esercizio = json.loads(json_esercizio)
    log: list[str] = []
    video_helper.scegli_ed_estrai(esercizio, output_dir=output_dir, logger=log.append)
    return {"esercizio": esercizio, "log": log}


def _copia_contenuto(sorgente: str, destinazione: str) -> None:
    """
    Copia SOLO i byte del file, non i metadati.

    shutil.copy2() (usata dall'app desktop) copia anche permessi e timestamp,
    e per farlo chiama os.chmod() sulla destinazione: sullo storage privato di
    un'app Android quella chiamata fallisce con "[Errno 13] Permission denied",
    anche se la cartella è dell'app stessa e la copia dei dati è appena
    riuscita. Il risultato era il peggiore possibile: il backup finiva sul
    disco completo e integro, ma l'eccezione arrivava PRIMA del ritaglio, che
    quindi non veniva mai eseguito (e il tentativo successivo, trovando il
    backup già presente, sembrava funzionare: un fallimento solo al primo
    tentativo, difficilissimo da riprodurre a mente).

    Di un backup ci interessa il contenuto, non i permessi: copyfile basta.
    """
    shutil.copyfile(sorgente, destinazione)


@risposta_json
def ritaglia(percorso: str, sinistra: float, alto: float, destra: float, basso: float) -> str:
    """
    Ritaglia in place un frame già estratto, riusando video_helper.crop_frame()
    (quindi con la stessa matematica e la stessa qualità JPEG del desktop:
    Pillow è installato anche qui, vedi app/build.gradle.kts).

    Prima del primo ritaglio salva una copia dell'originale accanto al frame,
    secondo la convenzione condivisa scheda_file.percorso_backup_frame(): è la
    stessa cosa che fa l'app Streamlit, ed è ciò che permette a
    ripristina_originale() di annullare il ritaglio e al bundle di conservare
    anche la versione non ritagliata. Il backup si crea una sola volta, così
    ritagli successivi restano annullabili fino all'immagine di partenza.
    """
    if not os.path.exists(percorso):
        raise ValueError(f"Il frame da ritagliare non esiste: {percorso}")

    backup = scheda_file.percorso_backup_frame(percorso)
    if not os.path.exists(backup):
        _copia_contenuto(percorso, backup)
    return video_helper.crop_frame(percorso, sinistra, alto, destra, basso)


@risposta_json
def ripristina_originale(percorso: str) -> str:
    """
    Riporta un frame ritagliato alla sua versione originale, ricopiando il
    backup creato da ritaglia(). Solleva ValueError (-> codice VALORE) se non
    esiste alcun backup, così l'interfaccia può disabilitare o spiegare il
    comando invece di fallire in silenzio.
    """
    backup = scheda_file.percorso_backup_frame(percorso)
    if not os.path.exists(backup):
        raise ValueError("Nessun originale da ripristinare: questo frame non è mai stato ritagliato.")
    _copia_contenuto(backup, percorso)
    return percorso


@risposta_json
def ha_backup_originale(percorso: str) -> bool:
    """Indica se esiste il backup pre-ritaglio, per abilitare il comando di ripristino nell'interfaccia."""
    return os.path.exists(scheda_file.percorso_backup_frame(percorso))


@risposta_json
def box_ritaglio_json(
    larghezza: int, altezza: int, sinistra: float, alto: float, destra: float, basso: float
) -> tuple:
    """Pura matematica (nessuna dipendenza da Pillow): per l'anteprima live del ritaglio lato Kotlin."""
    return video_helper.box_ritaglio((larghezza, altezza), sinistra, alto, destra, basso)


@risposta_json
def registra_backend_frame(estrattore) -> None:
    """
    Sostituisce ffmpeg (assente su Android) con un backend nativo. 'estrattore'
    è un oggetto Kotlin (vedi EstrattoreFrameNativo.kt) con un metodo pubblico
    estrai(streamUrl: String, timestampSecondi: Double, percorsoOutput: String): String
    Chaquopy espone gli oggetti Java/Kotlin passati a Python come attributi
    chiamabili, quindi 'estrattore.estrai(...)' richiama direttamente il
    metodo Kotlin. Il wrapper adatta la firma al contratto atteso da
    video_helper.imposta_backend_frame(): funzione(stream_url, timestamp_seconds,
    output_path) -> str.
    """

    def _backend(stream_url: str, timestamp_seconds: float, output_path: str) -> str:
        return estrattore.estrai(stream_url, float(timestamp_seconds), output_path)

    video_helper.imposta_backend_frame(_backend)
    return None


# --------------------------------------------------------------------------
# Google Docs
# --------------------------------------------------------------------------


@risposta_json
def genera_documento(json_esercizi: str, titolo: str, access_token: str, state_path: str = "") -> dict:
    """
    docs_service/drive_service sono costruiti qui dall'access_token (ottenuto
    lato Kotlin via AppAuth): get_credentials() (che aprirebbe un browser
    desktop) non viene mai chiamata su Android.
    """
    esercizi = json.loads(json_esercizi)
    docs_service, drive_service = _servizi_google_da_token(access_token)
    return google_docs_helper.create_workout_document(
        esercizi,
        titolo,
        docs_service=docs_service,
        drive_service=drive_service,
        state_path=state_path or None,
    )


@risposta_json
def aggiorna_media(
    doc_id: str,
    nome_esercizio: str,
    video_url: str,
    ts_start: float | None,
    ts_finish: float | None,
    access_token: str,
    state_path: str,
    output_dir: str,
) -> dict:
    docs_service, drive_service = _servizi_google_da_token(access_token)
    return google_docs_helper.update_exercise_media(
        doc_id,
        nome_esercizio,
        video_url=video_url or None,
        ts_start=ts_start,
        ts_finish=ts_finish,
        state_path=state_path or None,
        docs_service=docs_service,
        drive_service=drive_service,
        output_dir=output_dir,
    )


@risposta_json
def stato_generazione(state_path: str) -> dict | None:
    """Stato di ripresa (doc_id/titolo/esercizi) per l'avanzamento della generazione, o None."""
    return google_docs_helper.carica_stato(state_path)


# --------------------------------------------------------------------------
# Diagnostica
# --------------------------------------------------------------------------


@risposta_json
def versione_python() -> str:
    """Usata dalla schermata di prova per dimostrare che Chaquopy funziona."""
    return sys.version
