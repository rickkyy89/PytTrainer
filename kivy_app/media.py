"""Platform-agnostic flow controller for the per-exercise video & frame screen.

Mirrors the Streamlit "Video & Frame" tab behavior (ticket 07) on top of the
core helpers: YouTube search + relevance filter, manual URL override,
timestamp heuristics (10%/50% of duration), extraction through the injected
platform backend, percentage crop with ``*_orig.jpg`` backups and restore,
and user-image frame import.  All side effects arrive through injectable
callables so pytest covers the whole logic without network or Kivy.

The controller mutates the live exercise dict of the editor (same dictionaries
``SchedaEditorController`` owns) and calls ``on_change`` so the editor can
mark the bundle dirty.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from core.video_helper import (
    FrameExtractionError,
    VideoSearchError,
    crop_frame,
    extract_frame,
    extract_start_finish_frames,
    filtra_risultati_pertinenti,
    get_stream_info,
    get_video_info,
    importa_frame_da_immagine,
    search_youtube,
    scegli_ed_estrai,
)


class MediaFlowError(Exception):
    """A user-facing failure of the video & frame flow."""


def percorso_backup_frame(percorso_frame: str) -> str:
    """Conventional pre-crop backup path of a frame (``<frame>_orig.jpg``)."""
    radice, _ = os.path.splitext(percorso_frame)
    return f"{radice}_orig.jpg"


def url_con_inizio(url: str, secondi) -> str:
    """Ricostruisce l'URL YouTube con il frammento ``#t=SS`` (o ``&t=SSs``).

    Serve al pulsante Play: apre il video già posizionato sul secondo scelto.
    ``youtu.be`` usa il frammento ``#t``, gli altri formati il parametro
    ``t=<secondi>s`` preservando gli altri parametri della query.
    """
    url = str(url or "").strip()
    if not url:
        return url
    secondo = max(0, int(round(float(secondi or 0))))
    base, _, _frammento = url.partition("#")
    if "youtu.be/" in base:
        return f"{base}#t={secondo}s"
    testata, sep, query = base.partition("?")
    coppia_vista = False
    pezzi: list[str] = []
    for pezzo in query.split("&") if query else []:
        chiave, _, valore = pezzo.partition("=")
        if chiave in ("t", "start"):
            pezzi.append(f"{chiave}={secondo}s")
            coppia_vista = True
        else:
            pezzi.append(pezzo)
    if not coppia_vista:
        pezzi.append(f"t={secondo}s")
    return f"{testata}{sep}{'&'.join(pezzi)}" if pezzi else testata


@dataclass(frozen=True)
class SceltaVideo:
    """One searchable/selectable YouTube candidate rendered by the screen."""

    url: str
    title: str
    duration: float | None


class MediaFlowController:
    """Video search/selection, frame extraction, crop and image import."""

    def __init__(self, esercizio: dict, output_dir: str, *, backend=None,
                 log=None, on_change=None, search=search_youtube,
                 relevance_filter=filtra_risultati_pertinenti,
                 info_getter=get_video_info, extractor=extract_start_finish_frames,
                 auto_selector=scegli_ed_estrai, cropper=crop_frame,
                 image_importer=importa_frame_da_immagine, copier=shutil.copy2,
                 stream_resolver=get_stream_info, single_extractor=extract_frame):
        self._e = esercizio
        self._output_dir = output_dir
        self._backend = backend
        self._log = log if log is not None else []
        self._on_change = on_change or (lambda: None)
        self._search = search
        self._relevance_filter = relevance_filter
        self._info_getter = info_getter
        self._extractor = extractor
        self._auto_selector = auto_selector
        self._cropper = cropper
        self._image_importer = image_importer
        self._copier = copier
        self._stream_resolver = stream_resolver
        self._single_extractor = single_extractor
        self._scelte: list[SceltaVideo] = []
        self._durata: float | None = None
        self._titolo_video: str | None = None
        self._stream_cache: tuple[str, str, dict] | None = None

    # ------------------------------------------------------------------ stato

    @property
    def log(self) -> list[str]:
        return self._log

    @property
    def scelte(self) -> list[SceltaVideo]:
        """Relevant search results kept after filtering (top of the list first)."""
        return list(self._scelte)

    @property
    def video_url(self) -> str:
        return str(self._e.get("video_url") or "")

    @property
    def titolo_video(self) -> str | None:
        return self._titolo_video

    @property
    def ts_start(self) -> float | None:
        return self._e.get("ts_start")

    @property
    def ts_finish(self) -> float | None:
        return self._e.get("ts_finish")

    @property
    def durata(self) -> float | None:
        return self._durata

    def frame(self, suffisso: str) -> str | None:
        percorso = self._e.get(f"frame_{suffisso}")
        return percorso or None

    def frame_su_disco(self, suffisso: str) -> str | None:
        """Frame path only when the referenced JPEG still exists on disk."""
        percorso = self.frame(suffisso)
        return percorso if percorso and os.path.exists(percorso) else None

    def pronto(self) -> bool:
        return bool(self.frame_su_disco("start") and self.frame_su_disco("finish"))

    # ------------------------------------------------------------------ cerca

    def cerca(self) -> list[SceltaVideo]:
        """Search YouTube for the exercise name and keep the relevant results."""
        nome = str(self._e.get("nome") or "").strip()
        if not nome:
            raise MediaFlowError("Dai un nome all'esercizio prima di cercare il video.")
        try:
            risultati = self._search(nome)
        except VideoSearchError as exc:
            raise MediaFlowError(f"Ricerca YouTube fallita: {exc}") from exc
        pertinenti, scartati = self._relevance_filter(nome, risultati)
        for scarto in scartati:
            self._log.append(
                f"scartato '{scarto['video'].get('title')}': {scarto['motivo']}"
            )
        self._scelte = [
            SceltaVideo(video["webpage_url"], str(video.get("title") or ""),
                        video.get("duration"))
            for video in pertinenti
        ]
        if not self._scelte:
            self._log.append("nessun video pertinente trovato.")
        return self.scelte

    def seleziona(self, indice: int) -> SceltaVideo:
        """Pin one search result as the exercise video URL."""
        try:
            scelta = self._scelte[indice]
        except IndexError as exc:
            raise MediaFlowError("Video non piu' tra i risultati: esegui una nuova ricerca.") from exc
        self._e["video_url"] = scelta.url
        self._titolo_video = scelta.title
        self._durata = self._prova_durata(scelta.url, scelta.duration)
        self._applica_euristica_timestamp()
        self._on_change()
        return scelta

    def url_manuale(self, url: str) -> None:
        """Force a video URL typed by the user (skips search and filtering)."""
        url = str(url or "").strip()
        if not url:
            raise MediaFlowError("Inserisci un URL video non vuoto.")
        self._e["video_url"] = url
        self._durata = self._prova_durata(url, None)
        self._applica_euristica_timestamp()
        self._on_change()

    def proponi_euristica(self) -> None:
        """Force the 10%/50% proposal, overwriting any manual timestamps."""
        self._e["ts_start"] = None
        self._e["ts_finish"] = None
        if self.video_url and self._durata is None:
            self._durata = self._prova_durata(self.video_url, None)
        self._applica_euristica_timestamp()
        self._on_change()

    def assicura_durata(self) -> float | None:
        """Risolve la durata per un video proveniente dal manifest.

        Il controller costruito su un esercizio già completo non ha mai
        chiamato ``get_video_info``: lo scrub ne ha bisogno per l'escursione
        della pista e per il clamp dei timestamp.
        """
        if self._durata is None and self.video_url:
            self._durata = self._prova_durata(self.video_url, None)
        return self._durata

    def url_per_play(self, secondi=None) -> str:
        """URL del video posizionato a ``secondi`` (default: il timestamp start)."""
        url = self.video_url
        if not url:
            raise MediaFlowError("Seleziona prima un video.")
        if secondi is None:
            secondi = self.ts_start if self.ts_start is not None else 0
        return url_con_inizio(url, secondi)

    def imposta_timestamp(self, ts_start: float | None = None,
                          ts_finish: float | None = None) -> None:
        for chiave, valore in (("ts_start", ts_start), ("ts_finish", ts_finish)):
            if valore is None:
                continue
            if not isinstance(valore, (int, float)) or valore < 0:
                raise MediaFlowError(f"Timestamp {chiave} non valido: {valore}.")
            self._e[chiave] = float(valore)
        self._on_change()

    # ---------------------------------------------------------------- estrai

    def estrai(self, *, riestrai: bool = False) -> bool:
        """Extract START/FINISH frames; returns True when both are ready.

        Idempotent like ``scegli_ed_estrai``: existing frames on disk are kept
        unless ``riestrai`` forces a fresh extraction.  Timestamps must satisfy
        finish > start before any network/ffmpeg work (parity with Streamlit).
        """
        nome = str(self._e.get("nome") or "").strip()
        if not nome:
            raise MediaFlowError("Dai un nome all'esercizio prima di estrarre i frame.")
        if not riestrai and self.pronto():
            self._log.append("frame già presenti, nessuna estrazione.")
            return True
        if self.video_url:
            ts_start = self.ts_start if self.ts_start is not None else self._euristica(0.10)
            ts_finish = self.ts_finish if self.ts_finish is not None else self._euristica(0.50)
            if ts_finish <= ts_start:
                raise MediaFlowError(
                    "Correggi i timestamp prima di estrarre i frame: il FINISH deve "
                    "essere maggiore dello START."
                )
            try:
                percorso_start, percorso_finish = self._extractor(
                    self.video_url, ts_start, ts_finish, nome, self._output_dir,
                    ffmpeg_backend=self._backend,
                )
            except (VideoSearchError, FrameExtractionError) as exc:
                self._log.append(f"estrazione fallita per '{self.video_url}': {exc}")
                return False
            self._e["ts_start"], self._e["ts_finish"] = ts_start, ts_finish
            self._e["frame_start"], self._e["frame_finish"] = percorso_start, percorso_finish
            self._log.append(
                f"frame estratti da {self.video_url} (ts {ts_start:.1f}/{ts_finish:.1f})"
            )
            self._on_change()
            return True
        try:
            self._auto_selector(self._e, self._output_dir, self._log.append,
                                ffmpeg_backend=self._backend)
        except Exception as exc:  # scegli_ed_estrai non dovrebbe sollevare: guardia difensiva
            self._log.append(f"estrazione automatica fallita: {exc}")
        self._on_change()
        return self.pronto()

    # ------------------------------------------------------------------ crop

    def ritaglia(self, suffisso: str, sinistra: float, alto: float,
                 destra: float, basso: float) -> str:
        """Apply a percentage crop to one frame, backing the original up once."""
        percorso = self._frame_esistente(suffisso)
        backup = percorso_backup_frame(percorso)
        if not os.path.exists(backup):
            self._copier(percorso, backup)
        self._cropper(percorso, sinistra, alto, destra, basso)
        self._pulisci_anteprima(suffisso)
        self._on_change()
        return percorso

    def ripristina(self, suffisso: str) -> str:
        """Restore a frame from its ``*_orig.jpg`` backup (created by a crop)."""
        percorso = self._frame_esistente(suffisso)
        backup = percorso_backup_frame(percorso)
        if not os.path.exists(backup):
            raise MediaFlowError("Nessun originale da ripristinare per questo frame.")
        self._copier(backup, percorso)
        self._on_change()
        return percorso

    def puo_ripristinare(self, suffisso: str) -> bool:
        percorso = self._e.get(f"frame_{suffisso}")
        return bool(percorso and os.path.exists(percorso_backup_frame(percorso)))

    # -------------------------------------------------------------- anteprime

    def percorso_anteprima(self, suffisso: str) -> str:
        """Scratch path (outside the manifest) for the live crop preview."""
        return os.path.join(self._output_dir, f"_crop_preview_{suffisso}.jpg")

    def percorso_scrub(self, suffisso: str) -> str:
        """Scratch path for the scrub slider's live frame preview."""
        return os.path.join(self._output_dir, f"_scrub_preview_{suffisso}.jpg")

    def anteprima_scrub(self, suffisso: str, timestamp: float) -> str:
        """Extract a throwaway frame at ``timestamp`` for the scrub preview.

        Never mutates the manifest: it only resolves the stream (cached across
        calls, re-resolved once on a failed extraction like the real extractor)
        and writes a scratch JPEG under ``_scrub_preview_<suffisso>.jpg``.
        """
        if suffisso not in ("start", "finish"):
            raise MediaFlowError(f"Suffisso frame non valido: {suffisso}.")
        url = self.video_url
        if not url:
            raise MediaFlowError("Seleziona prima un video.")
        ts = max(0.0, float(timestamp))
        self.assicura_durata()
        if self._durata:
            ts = min(ts, max(0.0, self._durata - 0.1))
        os.makedirs(self._output_dir, exist_ok=True)
        dest = self.percorso_scrub(suffisso)
        stream_url, headers = self._stream_corrente(url)
        try:
            self._single_extractor(stream_url, ts, dest, headers,
                                   ffmpeg_backend=self._backend)
        except FrameExtractionError:
            self._stream_cache = None
            stream_url, headers = self._stream_corrente(url)
            try:
                self._single_extractor(stream_url, ts, dest, headers,
                                       ffmpeg_backend=self._backend)
            except (FrameExtractionError, VideoSearchError) as exc:
                raise MediaFlowError(f"Anteprima scrub fallita: {exc}") from exc
        return dest

    def _stream_corrente(self, url: str) -> tuple[str, dict]:
        """Resolve (and cache) the stream URL/headers for ``url``."""
        if self._stream_cache and self._stream_cache[0] == url:
            return self._stream_cache[1], self._stream_cache[2]
        try:
            stream_url, headers = self._stream_resolver(url)
        except VideoSearchError as exc:
            raise MediaFlowError(f"Stream non disponibile: {exc}") from exc
        self._stream_cache = (url, stream_url, headers)
        return stream_url, headers

    def anteprima_crop(self, suffisso: str, sinistra: float, alto: float,
                       destra: float, basso: float) -> str:
        """Render the pending crop to a scratch preview file (no mutation)."""
        percorso = self._frame_esistente(suffisso)
        anteprima = self.percorso_anteprima(suffisso)
        self._cropper(percorso, sinistra, alto, destra, basso, output_path=anteprima)
        return anteprima

    # ------------------------------------------------------- immagini proprie

    def importa_immagine(self, percorso_immagine: str, suffisso: str) -> str:
        """Use a user image (gallery/filesystem) as the START/FINISH frame."""
        nome = str(self._e.get("nome") or "").strip()
        if not nome:
            raise MediaFlowError("Dai un nome all'esercizio prima di importare un'immagine.")
        try:
            destinazione = self._image_importer(percorso_immagine, nome, suffisso,
                                                self._output_dir)
        except (FrameExtractionError, ValueError) as exc:
            raise MediaFlowError(str(exc)) from exc
        self._e[f"frame_{suffisso}"] = destinazione
        self._on_change()
        return destinazione

    # ------------------------------------------------------------------ hook

    def _frame_esistente(self, suffisso: str) -> str:
        if suffisso not in ("start", "finish"):
            raise MediaFlowError(f"Suffisso frame non valido: {suffisso}.")
        percorso = self._e.get(f"frame_{suffisso}")
        if not percorso or not os.path.exists(percorso):
            raise MediaFlowError("Frame non ancora estratto: niente su cui lavorare.")
        return percorso

    def _pulisci_anteprima(self, suffisso: str) -> None:
        try:
            os.remove(self.percorso_anteprima(suffisso))
        except OSError:
            pass

    def _prova_durata(self, url: str, nota: float | None) -> float | None:
        if nota:
            return float(nota)
        try:
            info = self._info_getter(url)
        except Exception:  # la durata e' solo euristica: non blocca mai il flusso
            self._log.append(f"impossibile recuperare la durata di {url}")
            return None
        self._titolo_video = info.get("title") or self._titolo_video
        durata = info.get("duration")
        return float(durata) if durata else None

    def _euristica(self, frazione: float) -> float:
        return (self._durata or 60) * frazione

    def _applica_euristica_timestamp(self) -> None:
        if self.ts_start is None:
            self._e["ts_start"] = self._euristica(0.10)
        if self.ts_finish is None:
            self._e["ts_finish"] = self._euristica(0.50)
