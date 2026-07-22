"""
Modulo di supporto per la ricerca di video YouTube (via yt-dlp) e l'estrazione
di frame START/FINISH da uno stream video (via ffmpeg), senza mai scaricare
il video completo su disco.
"""

from __future__ import annotations

import os
import re
import subprocess

import yt_dlp
from yt_dlp.utils import DownloadError


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


def _slugify(nome: str) -> str:
    """Converte il nome esercizio in uno slug sicuro per nomi di file (solo [a-z0-9_])."""
    slug = nome.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "esercizio"


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
    ritenta l'estrazione.
    """
    os.makedirs(output_dir, exist_ok=True)
    slug = _slugify(exercise_name)
    path_start = os.path.join(output_dir, f"{slug}_start.jpg")
    path_finish = os.path.join(output_dir, f"{slug}_finish.jpg")

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
