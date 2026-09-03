"""Google Doc export flow for one opened scheda (ticket 08).

Runs ``core.docs_helper.create_workout_document`` against the editor's ready
exercises (both frames on disk) with a ``state_path`` inside the bundle work
directory, so generation checkpoints after every exercise and resuming after
an interruption inserts only the missing ones.  ``progresso()`` lets the UI
poll the state file while generation runs on a worker thread.  On success the
state is persisted into the ``.scheda`` bundle through the editor's own save
flow (bundle rewrite + Drive upload), and ``documento_rigenerato`` surfaces
the "state pointed to a deleted doc, rebuilt with a new URL" condition.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.docs_helper import carica_stato, create_workout_document
from core.scheda_file import percorso_stato


class DocExportError(Exception):
    """A user-facing failure of the document generation flow."""


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
                 stato_loader=carica_stato):
        self._editor = editor
        self._credential_provider = credential_provider
        self._base_dir = base_dir
        self._creator = creator
        self._stato_loader = stato_loader
        self._state_path: str | None = None
        self._totale_sessione: int = 0
        self._baseline: int = 0
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

    def genera(self) -> dict:
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
        self._baseline = self._conteggio_stato()
        self._ultimo_inseriti = 0
        riepilogo = self.riepilogo()
        try:
            risultato = self._creator(
                [dict(esercizio) for esercizio in pronti], riepilogo.titolo,
                state_path=self._state_path,
                credential_provider=self._credential_provider,
                base_dir=self._base_dir,
            )
        except Exception:
            self._persisti_checkpoint()  # meglio un bundle con checkpoint parziale
            raise
        risultato["salvataggio"] = self._editor.salva()
        return risultato

    def progresso(self) -> tuple[int, int]:
        """(checkpointed exercises, total of this session) for the UI poll."""
        totale = self._totale_sessione or len(self.esercizi_pronti())
        current = self._conteggio_stato()
        inseriti = min(totale, max(self._ultimo_inseriti, current - self._baseline))
        self._ultimo_inseriti = inseriti
        return inseriti, totale

    def _conteggio_stato(self) -> int:
        """Exercises recorded in the checkpoint state; 0 when missing/broken."""
        if not self._state_path:
            return 0
        try:
            stato = self._stato_loader(self._state_path)
        except Exception:
            return self._ultimo_inseriti + self._baseline
        return len(stato.get("esercizi", [])) if stato else 0

    def _persisti_checkpoint(self) -> None:
        try:
            self._editor.salva()
        except Exception:
            pass
