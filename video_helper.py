"""
Modulo di supporto per la ricerca di video YouTube (via yt-dlp) e l'estrazione
di frame START/FINISH da uno stream video (via ffmpeg), senza mai scaricare
il video completo su disco.
"""

from __future__ import annotations

import math
import os
import re
import subprocess

import yt_dlp
from PIL import Image, ImageOps
from yt_dlp.utils import DownloadError

from csv_utils import slugify, slugs_unici


class VideoSearchError(Exception):
    """Sollevata quando la ricerca o la risoluzione di un video YouTube fallisce."""


class FrameExtractionError(Exception):
    """Sollevata quando ffmpeg non riesce a estrarre un frame dallo stream."""


def search_youtube(query: str, max_results: int = 3) -> list[dict]:
    """
    Cerca su YouTube i video relativi a un esercizio e restituisce una lista
    di dizionari con le informazioni essenziali per la selezione da UI.

    La query effettiva inviata a YouTube viene arricchita con la frase
    "esecuzione corretta" per privilegiare video tutorial/tecnica.
    """
    ricerca = f"{query} esecuzione corretta"
    opzioni = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opzioni) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{ricerca}", download=False)
    except DownloadError as exc:
        raise VideoSearchError(
            f"Impossibile cercare video su YouTube per '{query}': {exc}"
        ) from exc

    voci = info.get("entries") or [] if info else []
    risultati = []
    for voce in voci:
        if not voce:
            continue
        video_id = voce.get("id", "")
        # extract_flat spesso non fornisce la thumbnail: usiamo il fallback standard.
        thumbnail = voce.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        webpage_url = voce.get("webpage_url") or voce.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        risultati.append(
            {
                "id": video_id,
                "title": voce.get("title", "Titolo sconosciuto"),
                "thumbnail": thumbnail,
                "duration": voce.get("duration"),
                "webpage_url": webpage_url,
            }
        )
    return risultati


def get_stream_url(video_url: str) -> str:
    """
    Risolve l'URL diretto dello stream video (senza scaricarlo) per poterlo
    passare a ffmpeg. Restituisce l'URL del miglior formato mp4 disponibile
    fino a 720p, con fallback a formati alternativi.
    """
    opzioni = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
    }
    try:
        with yt_dlp.YoutubeDL(opzioni) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except DownloadError as exc:
        raise VideoSearchError(
            f"Impossibile recuperare lo stream del video '{video_url}': {exc}"
        ) from exc

    url = info.get("url")
    if url:
        return url

    # Fallback: cerca l'url nei formati richiesti (es. video+audio separati).
    for formato in info.get("requested_formats") or []:
        if formato.get("url"):
            return formato["url"]

    # Ultimo fallback: scorre tutti i formati disponibili e prende l'ultimo
    # con url valido e traccia video presente.
    formati = info.get("formats") or []
    for formato in reversed(formati):
        if formato.get("url") and formato.get("vcodec") not in (None, "none"):
            return formato["url"]

    raise VideoSearchError(
        f"Nessuno stream video valido trovato per '{video_url}'."
    )


def extract_frame(stream_url: str, timestamp_seconds: float, output_path: str) -> str:
    """
    Estrae un singolo frame dallo stream all'istante indicato usando ffmpeg,
    scaricando solo i byte necessari grazie al seek rapido (-ss prima di -i).
    """
    comando = [
        "ffmpeg",
        "-ss", str(timestamp_seconds),
        "-i", stream_url,
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        output_path,
    ]
    try:
        risultato = subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise FrameExtractionError(
            f"Timeout durante l'estrazione del frame al secondo {timestamp_seconds}."
        ) from exc

    file_ok = os.path.exists(output_path) and os.path.getsize(output_path) > 0
    if risultato.returncode != 0 or not file_ok:
        stderr_text = risultato.stderr.decode("utf-8", errors="ignore")
        ultime_righe = "\n".join(stderr_text.strip().splitlines()[-10:])
        raise FrameExtractionError(
            f"ffmpeg non è riuscito a estrarre il frame al secondo {timestamp_seconds}: {ultime_righe}"
        )
    return output_path


# Alias mantenuto per compatibilità interna: la slugificazione canonica ora
# vive in csv_utils (riusata anche da google_docs_helper per i file di stato
# e i named range dei documenti).
_slugify = slugify


def _percorso_frame_unico(output_dir: str, slug: str, suffisso: str) -> str:
    """
    Restituisce un percorso frame non collidente in output_dir. Se
    "<slug>_<suffisso>.jpg" esiste già, prova "<slug>_2_<suffisso>.jpg" ecc.
    """
    candidato = os.path.join(output_dir, f"{slug}_{suffisso}.jpg")
    if not os.path.exists(candidato):
        return candidato
    n = 2
    while True:
        alternativo = os.path.join(output_dir, f"{slug}_{n}_{suffisso}.jpg")
        if not os.path.exists(alternativo):
            return alternativo
        n += 1


def extract_start_finish_frames(
    video_url: str,
    ts_start: float,
    ts_finish: float,
    exercise_name: str,
    output_dir: str = "frames",
) -> tuple[str, str]:
    """
    Risolve lo stream URL una sola volta ed estrae i frame START e FINISH
    per l'esercizio indicato, salvandoli in output_dir. Se lo stream URL
    risulta scaduto (errore di ffmpeg), viene ri-risolto una volta e si
    ritenta l'estrazione. Se esiste già un file con lo stesso slug, usa un
    suffisso numerico (_2, _3) per non sovrascrivere l'esercizio omonimo.
    """
    os.makedirs(output_dir, exist_ok=True)
    slug = _slugify(exercise_name)
    # Usa nomi unici per non sovrascrivere un omonimo già estratto
    path_start = _percorso_frame_unico(output_dir, slug, "start")
    path_finish = _percorso_frame_unico(output_dir, slug, "finish")

    stream_url = get_stream_url(video_url)

    def _estrai_con_retry(timestamp: float, path: str) -> str:
        nonlocal stream_url
        try:
            return extract_frame(stream_url, timestamp, path)
        except FrameExtractionError:
            # Lo stream url potrebbe essere scaduto: lo ri-risolviamo e riproviamo una volta.
            stream_url = get_stream_url(video_url)
            return extract_frame(stream_url, timestamp, path)

    _estrai_con_retry(ts_start, path_start)
    _estrai_con_retry(ts_finish, path_finish)

    return path_start, path_finish


# Stopword basilari italiane e inglesi, usate SOLO per estrarre le parole
# significative dal NOME dell'esercizio (non dal titolo del video: parole
# come "tutorial" o "esercizio" possono comparire legittimamente nel titolo
# e non vanno quindi rimosse da lì). Lista volutamente corta.
STOPWORD_NOME_ESERCIZIO = {
    # italiano
    "il", "lo", "la", "di", "da", "per", "con", "come",
    # inglese
    "the", "a", "of", "for", "with", "how", "to", "and", "in", "best",
}


def _normalizza_testo(testo: str) -> list[str]:
    """Minuscolo, rimozione della punteggiatura, split in parole non vuote."""
    testo = testo.lower()
    testo = re.sub(r"[^\w\s]", " ", testo, flags=re.UNICODE)
    return [parola for parola in testo.split() if parola]


def filtra_risultati_pertinenti(
    nome_esercizio: str,
    risultati: list[dict],
    durata_min: float = 15,
    durata_max: float = 1200,
) -> tuple[list[dict], list[dict]]:
    """
    Filtra i risultati di search_youtube() scartando quelli non pertinenti al
    nome dell'esercizio (in base alle parole significative del nome trovate
    per parola intera nel titolo del video) o con durata fuori dal range
    plausibile [durata_min, durata_max] per un tutorial.

    Restituisce (pertinenti, scartati): scartati è una lista di dizionari
    {"video": <dict risultato>, "motivo": <str in italiano>}.
    """
    parole_nome = _normalizza_testo(nome_esercizio)
    parole_significative = [parola for parola in parole_nome if parola not in STOPWORD_NOME_ESERCIZIO]
    if not parole_significative:
        # Nome composto solo da stopword: usiamo comunque le parole originali
        # per non scartare sistematicamente tutti i risultati.
        parole_significative = parole_nome
    n_significative = len(parole_significative)

    if n_significative <= 1:
        soglia = 1
    else:
        # Servono almeno 2 corrispondenze, oppure il 50% (arrotondato per
        # eccesso) delle parole significative, se maggiore di 2.
        soglia = max(2, math.ceil(n_significative * 0.5))

    pertinenti = []
    scartati = []
    for video in risultati:
        durata = video.get("duration")
        if durata is not None and not (durata_min <= durata <= durata_max):
            scartati.append({"video": video, "motivo": "durata"})
            continue

        parole_titolo = set(_normalizza_testo(video.get("title", "")))
        corrispondenze = sum(1 for parola in parole_significative if parola in parole_titolo)
        if corrispondenze >= soglia:
            pertinenti.append(video)
        else:
            scartati.append(
                {
                    "video": video,
                    "motivo": (
                        f"pertinenza insufficiente ({corrispondenze}/{n_significative} parole "
                        f"del nome trovate nel titolo, ne servono almeno {soglia})"
                    ),
                }
            )
    return pertinenti, scartati


def get_video_info(video_url: str) -> dict:
    """
    Recupera durata e titolo di un video YouTube senza scaricarlo (skip
    download, nessun extract_flat). Utile per calcolare l'euristica 10%/50%
    sui timestamp quando il video è forzato via VideoURL nel manifest e i
    timestamp non sono indicati.
    """
    opzioni = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opzioni) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except DownloadError as exc:
        raise VideoSearchError(
            f"Impossibile recuperare le informazioni del video '{video_url}': {exc}"
        ) from exc

    return {
        "duration": info.get("duration") if info else None,
        "title": (info.get("title") if info else None) or "Titolo sconosciuto",
    }


def scegli_ed_estrai(esercizio: dict, output_dir: str = "frames", logger=print) -> dict:
    """
    Orchestrazione completa della scelta video + estrazione frame per un
    singolo esercizio del manifest. Muta e ritorna lo stesso dizionario
    esercizio (aggiornandolo con video_url/ts_start/ts_finish/frame_start/
    frame_finish in caso di successo).

    Ordine delle decisioni:
      1. Se i frame indicati nel manifest esistono già su disco, non fa
         nulla (li considera già pronti).
      2. Se è presente un VideoURL forzato nel manifest, lo usa direttamente
         (salta ricerca e filtro di pertinenza).
      3. Altrimenti cerca su YouTube, scarta i risultati non pertinenti
         (loggando il motivo) e tenta l'estrazione sui risultati pertinenti
         in ordine, fermandosi al primo che ha successo.

    In caso di nessun video utilizzabile, logga e lascia i campi frame a
    None: non solleva mai eccezioni (l'esercizio va semplicemente escluso a
    valle dalla generazione del documento).
    """
    nome = esercizio.get("nome", "")

    frame_start = esercizio.get("frame_start")
    frame_finish = esercizio.get("frame_finish")
    if frame_start and frame_finish and os.path.exists(frame_start) and os.path.exists(frame_finish):
        logger(f"[{nome}] frame già presenti, salto.")
        return esercizio

    video_url_forzato = esercizio.get("video_url")
    if video_url_forzato:
        ts_start = esercizio.get("ts_start")
        ts_finish = esercizio.get("ts_finish")
        if ts_start is None or ts_finish is None:
            try:
                info = get_video_info(video_url_forzato)
            except VideoSearchError as errore:
                logger(f"[{nome}] impossibile recuperare la durata di '{video_url_forzato}': {errore}")
                return esercizio
            durata = info.get("duration") or 60
            if ts_start is None:
                ts_start = durata * 0.10
            if ts_finish is None:
                ts_finish = durata * 0.50
        try:
            percorso_start, percorso_finish = extract_start_finish_frames(
                video_url_forzato, ts_start, ts_finish, nome, output_dir
            )
        except (VideoSearchError, FrameExtractionError) as errore:
            logger(f"[{nome}] estrazione fallita dal video forzato '{video_url_forzato}': {errore}")
            return esercizio

        esercizio["video_url"] = video_url_forzato
        esercizio["ts_start"] = ts_start
        esercizio["ts_finish"] = ts_finish
        esercizio["frame_start"] = percorso_start
        esercizio["frame_finish"] = percorso_finish
        logger(f"[{nome}] video forzato dal manifest usato: {video_url_forzato}")
        return esercizio

    try:
        risultati = search_youtube(nome)
    except VideoSearchError as errore:
        logger(f"[{nome}] ricerca YouTube fallita: {errore}")
        return esercizio

    pertinenti, scartati = filtra_risultati_pertinenti(nome, risultati)
    for scarto in scartati:
        logger(f"[{nome}] scartato '{scarto['video'].get('title')}': {scarto['motivo']}")

    for video in pertinenti:
        durata = video.get("duration") or 60
        ts_start = esercizio.get("ts_start")
        ts_finish = esercizio.get("ts_finish")
        if ts_start is None:
            ts_start = durata * 0.10
        if ts_finish is None:
            ts_finish = durata * 0.50
        try:
            percorso_start, percorso_finish = extract_start_finish_frames(
                video["webpage_url"], ts_start, ts_finish, nome, output_dir
            )
        except (VideoSearchError, FrameExtractionError) as errore:
            logger(f"[{nome}] estrazione fallita per '{video.get('title')}': {errore}")
            continue

        esercizio["video_url"] = video["webpage_url"]
        esercizio["ts_start"] = ts_start
        esercizio["ts_finish"] = ts_finish
        esercizio["frame_start"] = percorso_start
        esercizio["frame_finish"] = percorso_finish
        logger(f"[{nome}] video scelto: '{video.get('title')}' ({video['webpage_url']})")
        return esercizio

    logger(f"[{nome}] nessun video utilizzabile trovato, frame lasciati vuoti.")
    return esercizio


def box_ritaglio(
    size: tuple[int, int],
    sinistra_pct: float = 0.0,
    alto_pct: float = 0.0,
    destra_pct: float = 0.0,
    basso_pct: float = 0.0,
) -> tuple[int, int, int, int]:
    """
    Calcola il box in pixel (sinistra, alto, destra, basso), nel formato
    atteso da Image.crop(), a partire dalle percentuali di ritaglio per lato
    e dalle dimensioni (larghezza, altezza) dell'immagine originale.

    Ogni percentuale deve essere compresa in [0, 45] e sinistra_pct +
    destra_pct deve restare sotto 90 (così come alto_pct + basso_pct),
    altrimenti il ritaglio azzererebbe o invertirebbe l'intera larghezza o
    altezza: in questi casi solleva ValueError con un messaggio in italiano.
    Pubblica (non prefissata con "_") perché riusata anche da app.py per
    l'anteprima live del ritaglio, senza duplicare la formula.
    """
    for nome_percentuale, valore in (
        ("sinistra_pct", sinistra_pct),
        ("alto_pct", alto_pct),
        ("destra_pct", destra_pct),
        ("basso_pct", basso_pct),
    ):
        if not (0 <= valore <= 45):
            raise ValueError(
                f"Percentuale di ritaglio '{nome_percentuale}' non valida: {valore}. "
                "Deve essere compresa tra 0 e 45."
            )
    if sinistra_pct + destra_pct >= 90:
        raise ValueError(
            "La somma delle percentuali di ritaglio sinistra e destra deve essere "
            f"minore di 90 (ricevuto {sinistra_pct + destra_pct})."
        )
    if alto_pct + basso_pct >= 90:
        raise ValueError(
            "La somma delle percentuali di ritaglio alto e basso deve essere minore "
            f"di 90 (ricevuto {alto_pct + basso_pct})."
        )

    larghezza, altezza = size
    sinistra = round(larghezza * sinistra_pct / 100)
    alto = round(altezza * alto_pct / 100)
    destra = round(larghezza * (1 - destra_pct / 100))
    basso = round(altezza * (1 - basso_pct / 100))
    return (sinistra, alto, destra, basso)


def crop_frame(
    image_path: str,
    sinistra_pct: float = 0.0,
    alto_pct: float = 0.0,
    destra_pct: float = 0.0,
    basso_pct: float = 0.0,
    output_path: str | None = None,
) -> str:
    """
    Ritaglia un frame estratto (START o FINISH) in base alle percentuali
    indicate per ciascun lato (sinistra/alto/destra/basso, vedi
    box_ritaglio() per i vincoli), salvandolo come JPEG (quality=90).

    Se output_path non è indicato, sovrascrive image_path. Le immagini con
    canale alpha vengono convertite in RGB prima del salvataggio (il formato
    JPEG non lo supporta). Restituisce il percorso del file scritto.
    """
    output_path = output_path or image_path
    with Image.open(image_path) as immagine:
        box = box_ritaglio(immagine.size, sinistra_pct, alto_pct, destra_pct, basso_pct)
        ritagliata = immagine.crop(box)
        if ritagliata.mode != "RGB":
            ritagliata = ritagliata.convert("RGB")
        ritagliata.save(output_path, "JPEG", quality=90)
    return output_path


def importa_frame_da_immagine(
    image_path: str,
    exercise_name: str,
    suffisso: str,
    output_dir: str = "frames",
) -> str:
    """
    Usa un'immagine dell'utente al posto del frame estratto dal video: la
    converte in JPEG e la salva in output_dir con lo stesso nome che avrebbe
    prodotto extract_start_finish_frames() ("<slug>_start.jpg" /
    "<slug>_finish.jpg"), così tutto il resto della pipeline (ritaglio,
    bundle .scheda, upload nel Google Doc) la tratta come un frame qualsiasi.
    Un eventuale frame già presente per quell'esercizio viene sostituito.

    Accetta qualunque formato leggibile da PIL (PNG, WEBP, HEIC via plugin,
    screenshot, foto...): l'orientamento EXIF viene applicato e la
    trasparenza appiattita su fondo bianco, perché il JPEG non la supporta.

    suffisso deve essere "start" o "finish". Solleva FrameExtractionError se
    il file non esiste o non è un'immagine leggibile, ValueError se il
    suffisso non è valido. Restituisce il percorso del JPEG scritto.
    """
    if suffisso not in ("start", "finish"):
        raise ValueError(f"Suffisso frame non valido: '{suffisso}' (attesi 'start' o 'finish').")
    if not image_path or not os.path.exists(image_path):
        raise FrameExtractionError(f"L'immagine '{image_path}' non esiste.")

    os.makedirs(output_dir, exist_ok=True)
    slug = _slugify(exercise_name)
    output_path = os.path.join(output_dir, f"{slug}_{suffisso}.jpg")

    try:
        with Image.open(image_path) as immagine:
            immagine = ImageOps.exif_transpose(immagine)
            if immagine.mode in ("RGBA", "LA", "P"):
                convertita = immagine.convert("RGBA")
                sfondo = Image.new("RGB", convertita.size, (255, 255, 255))
                sfondo.paste(convertita, mask=convertita.split()[-1])
                immagine = sfondo
            elif immagine.mode != "RGB":
                immagine = immagine.convert("RGB")
            immagine.save(output_path, "JPEG", quality=90)
    except (OSError, ValueError) as exc:
        raise FrameExtractionError(
            f"Impossibile usare '{os.path.basename(image_path)}' come frame: "
            f"non è un'immagine leggibile ({exc})."
        ) from exc

    # Il backup pre-ritaglio dell'immagine precedente si riferisce a un frame
    # che non esiste più: lasciarlo renderebbe "Ripristina originale" un
    # ripristino della vecchia immagine.
    backup = f"{os.path.splitext(output_path)[0]}_orig.jpg"
    if os.path.exists(backup):
        try:
            os.remove(backup)
        except OSError:
            pass

    return output_path
