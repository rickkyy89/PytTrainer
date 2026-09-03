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
        riepilogo = self.riepilogo()
        risultato = self._creator(
            pronti, riepilogo.titolo, state_path=self._state_path,
            credential_provider=self._credential_provider,
            base_dir=self._base_dir,
        )
        risultato["salvataggio"] = self._editor.salva()
        return risultato

    def progresso(self) -> tuple[int, int]:
        """(checkpointed exercises, total of this session) for the UI poll."""
        totale = self._totale_sessione or len(self.esercizi_pronti())
        if not self._state_path:
            return 0, totale
        try:
            stato = self._stato_loader(self._state_path)
        except Exception:
            return 0, totale
        inseriti = len(stato.get("esercizi", [])) if stato else 0
        return inseriti, totale
