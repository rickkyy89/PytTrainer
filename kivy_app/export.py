"""Google Doc export flow for one opened scheda (ticket 08).

Runs ``core.docs_helper.create_workout_document`` against the editor's ready
exercises (both frames on disk) with a ``state_path`` inside the bundle work
directory, so generation checkpoints after every exercise and resuming after
an interruption inserts only the missing ones.  ``progresso()`` lets the UI
poll the state file while generation runs on a worker thread.  On success the
state is synced to Drive through the editor's save flow. Each intermediate
checkpoint is already persisted locally into the bundle, independently of UI
polling and exception handlers. ``documento_rigenerato`` surfaces a new URL
after deletion, partial mutation, remote damage or explicit regeneration.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.docs_helper import carica_stato, create_workout_document
from core.scheda_file import percorso_stato


class DocExportError(Exception):
    """A user-facing failure of the document generation flow."""


class PdfExportError(DocExportError):
    """The generated Google Doc could not be materialized as a local PDF."""


PDF_MIME_TYPE = "application/pdf"
MAX_PDF_FILENAME_BYTES = 180
WINDOWS_RESERVED_STEMS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class ExportRiepilogo:
    """Confirmation data shown before launching generation."""

    pronti: int
    totali: int
    titolo: str


class DocExportController:
    """Prepare, run and persist the Google Doc generation of an editor."""

    def __init__(self, editor, *, credential_provider=None, base_dir=None,
                 creator=create_workout_document,
                 stato_loader=carica_stato, drive_service_factory=None,
                 pdf_cache_dir=None, background_guard=None):
        self._editor = editor
        self._background_guard = background_guard
        self._credential_provider = credential_provider
        self._base_dir = base_dir
        self._creator = creator
        self._stato_loader = stato_loader
        self._drive_service_factory = drive_service_factory or self._build_drive_service
        default_cache = Path(base_dir or Path(editor.percorso_bundle).parent) / "drive-cache" / "pdf"
        self._pdf_cache_dir = Path(pdf_cache_dir or default_cache)
        self._state_path: str | None = None
        self._totale_sessione: int = 0
        self._ultimo_inseriti: int = 0

    # ------------------------------------------------------------- prepara

    def esercizi_pronti(self) -> list[dict]:
        """Exercises whose START and FINISH frames still exist on disk."""
        pronti = []
        for esercizio in self._editor.esercizi:
            start = esercizio.get("frame_start")
            finish = esercizio.get("frame_finish")
            if start and finish and os.path.exists(start) and os.path.exists(finish):
                pronti.append(esercizio)
        return pronti

    def riepilogo(self) -> ExportRiepilogo:
        totali = len(self._editor.esercizi)
        pronti = len(self.esercizi_pronti())
        titolo = self._editor.titolo or self._titolo_default()
        return ExportRiepilogo(pronti=pronti, totali=totali, titolo=titolo)

    def _titolo_default(self) -> str:
        nome = os.path.basename(str(self._editor.percorso_bundle))
        return nome[:-len(".scheda")] if nome.endswith(".scheda") else nome

    # --------------------------------------------------------------- genera

    def genera(self, *, force_regenerate=False) -> dict:
        """Generate/resume the document, then persist the state into the bundle.

        Returns the ``create_workout_document`` result plus a ``salvataggio``
        entry carrying the editor save outcome (UploadResult or SyncConflict).
        The creator receives a snapshot of the ready exercises so concurrent
        UI edits cannot mutate the document mid-generation, and a failed
        generation still pushes the latest checkpoint into the bundle.
        """
        if not self._editor.cartella_lavoro:
            raise DocExportError("Scheda senza cartella di lavoro: impossibile esportare.")
        pronti = self.esercizi_pronti()
        if not pronti:
            raise DocExportError(
                "Nessun esercizio pronto: servono i frame START e FINISH (ticket 07)."
            )
        self._state_path = percorso_stato(self._editor.cartella_lavoro)
        self._totale_sessione = len(pronti)
        self._ultimo_inseriti = 0
        riepilogo = self.riepilogo()
        try:
            if self._background_guard:
                self._background_guard.start()
            options = {"force_regenerate": True} if force_regenerate else {}
            risultato = self._creator(
                [dict(esercizio) for esercizio in pronti], riepilogo.titolo,
                state_path=self._state_path,
                credential_provider=self._credential_provider,
                base_dir=self._base_dir,
                checkpoint_callback=self._editor.salva_locale,
                **options,
            )
            risultato["salvataggio"] = self._editor.salva()
            return risultato
        except Exception:
            self._persisti_checkpoint()  # meglio un bundle con checkpoint parziale
            raise
        finally:
            if self._background_guard:
                self._background_guard.stop()

    def esporta_pdf(self, document_id: str) -> Path:
        """Export ``document_id`` through Drive and atomically publish its PDF.

        The final path is stable and human-readable, while the download first
        lands in a same-directory temporary file.  Thus a failed/partial Drive
        response never replaces a previously usable cached export.
        """
        if not str(document_id or "").strip():
            raise PdfExportError("Documento Google senza ID: impossibile esportare il PDF.")
        temporary: Path | None = None
        try:
            if self._background_guard:
                self._background_guard.start()
            content = self._scarica_pdf(document_id)
            if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
                raise PdfExportError("Drive non ha restituito un PDF valido.")

            self._pdf_cache_dir.mkdir(parents=True, exist_ok=True)
            destination = self._pdf_cache_dir / f"{self._pdf_filename()}.pdf"
            descriptor, raw_path = tempfile.mkstemp(
                prefix=f".{destination.stem}-", suffix=".tmp",
                dir=str(self._pdf_cache_dir),
            )
            temporary = Path(raw_path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            temporary = None
            return destination
        except PdfExportError:
            raise
        except Exception as exc:
            raise PdfExportError(f"Esportazione PDF fallita: {exc}") from exc
        finally:
            if self._background_guard:
                self._background_guard.stop()
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def _pdf_filename(self) -> str:
        title = self.riepilogo().titolo.strip() or "scheda-allenamento"
        # Keep readable Unicode/casing; only filesystem separators/control and
        # Windows-reserved punctuation are replaced.
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", title).strip(" .-")
        cleaned = cleaned or "scheda-allenamento"
        windows_device_stem = cleaned.split(".", 1)[0].rstrip(" .").upper()
        if windows_device_stem in WINDOWS_RESERVED_STEMS:
            cleaned = f"_{cleaned}"

        stem_budget = MAX_PDF_FILENAME_BYTES - len(".pdf".encode("ascii"))
        encoded = cleaned.encode("utf-8")
        if len(encoded) > stem_budget:
            cleaned = encoded[:stem_budget].decode("utf-8", errors="ignore").rstrip(" .-")
        return cleaned or "scheda-allenamento"

    def _scarica_pdf(self, document_id: str) -> bytes:
        """Download once, with one fresh-service retry after an auth failure."""
        from core.docs_helper import SCOPES

        for attempt in range(2):
            try:
                credentials = self._credential_provider.get_credentials(SCOPES)
                from core.google_retry import safe_service
                drive = safe_service(self._drive_service_factory(credentials))
                return drive.files().export(
                    fileId=document_id, mimeType=PDF_MIME_TYPE,
                ).execute()
            except Exception as exc:
                if attempt == 0 and self._is_auth_error(exc) and self._riautentica():
                    continue
                raise
        raise AssertionError("Ciclo di esportazione PDF terminato senza risultato.")

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        return getattr(getattr(exc, "resp", None), "status", None) in (401, 403)

    def _riautentica(self) -> bool:
        riautentica = getattr(self._credential_provider, "riautentica", None)
        if riautentica is None:
            return False
        try:
            return bool(riautentica())
        except Exception:
            return False

    @staticmethod
    def _build_drive_service(credentials):
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    def progresso(self) -> tuple[int, int]:
        """(checkpointed exercises, total of this session) for the UI poll."""
        totale = self._totale_sessione or len(self.esercizi_pronti())
        current = self._conteggio_stato()
        inseriti = min(totale, current)
        self._ultimo_inseriti = inseriti
        return inseriti, totale

    def _conteggio_stato(self) -> int:
        """Exercises recorded in the checkpoint state; 0 when missing/broken."""
        if not self._state_path:
            return 0
        try:
            stato = self._stato_loader(self._state_path)
        except Exception:
            return self._ultimo_inseriti
        return len(stato.get("esercizi", [])) if stato else 0

    def _persisti_checkpoint(self) -> None:
        try:
            self._editor.salva_locale()
        except Exception:
            pass
