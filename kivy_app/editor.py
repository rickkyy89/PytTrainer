"""Editor-domain behavior for one opened .scheda, free of any Kivy import.

``SchedaEditorController`` owns the mutable exercise list of an opened bundle
and the unsaved-changes flag.  Persistence is two-step: rewrite the bundle via
``core.scheda_file.salva_scheda`` (keeping frames, state and title) then upload
through an injected callable.  A ``SyncConflict`` from the upload is returned
verbatim for the UI (ticket 10 decides the resolution policy).
"""

from __future__ import annotations

from pathlib import Path

from core.csv_utils import parse_esercizi_csv, trova_duplicati_slug
from core.drive_sync import SyncConflict
from core.scheda_file import percorso_stato, salva_scheda, titolo_scheda


CAMPI_EDITABILI = ("nome", "spiegazione", "note", "ripetizioni", "recupero", "gruppo")

ESERCIZIO_VUOTO = {
    "nome": "", "spiegazione": "", "note": "", "ripetizioni": "", "recupero": "",
    "gruppo": "", "video_url": "", "ts_start": None, "ts_finish": None,
    "frame_start": None, "frame_finish": None,
}


class EditorValidationError(Exception):
    """A user-facing edit or save that the editor refuses to perform."""


class SchedaEditorController:
    """In-memory editing of the exercises of one bundle plus its save flow."""

    def __init__(self, esercizi: list[dict], *, percorso_bundle: str,
                 cartella_lavoro: str | None = None, titolo: str | None = None,
                 save_scheda=salva_scheda, upload=None, path_cls=Path):
        self._esercizi = esercizi
        self._percorso = percorso_bundle
        self._lavoro = cartella_lavoro
        self._titolo = titolo
        self._save_scheda = save_scheda
        self._upload = upload
        self._path_cls = path_cls
        self._dirty = False

    @property
    def esercizi(self) -> list[dict]:
        """Live exercise dicts; view code reads them, writes go through methods."""
        return self._esercizi

    @property
    def percorso_bundle(self) -> str:
        return self._percorso

    @property
    def cartella_lavoro(self) -> str | None:
        return self._lavoro

    def output_frames(self) -> str:
        """Frames directory of this bundle (ticket 07 extraction target)."""
        if not self._lavoro:
            raise EditorValidationError("Editor senza cartella di lavoro: frame non gestibili.")
        from core.scheda_file import cartella_frames
        return cartella_frames(self._lavoro)

    @property
    def sporco(self) -> bool:
        return self._dirty

    def marca_modifica(self) -> None:
        """Flag external mutations (video & frame flow of ticket 07) as unsaved."""
        self._dirty = True

    def conferma_salvataggio(self) -> None:
        """Clear the dirty flag once an out-of-band conflict resolution synced the bundle."""
        self._dirty = False

    @property
    def titolo(self) -> str | None:
        return self._titolo

    def aggiorna(self, indice: int, **campi: str) -> None:
        non_locali = set(campi) - set(CAMPI_EDITABILI)
        if non_locali:
            raise EditorValidationError(f"Campo non modificabile: {sorted(non_locali)[0]}.")
        esercizio = self._esame(indice)
        for chiave, valore in campi.items():
            esercizio[chiave] = str(valore)
        self._dirty = True

    def aggiungi(self, dopo: int | None = None) -> int:
        """Insert a blank exercise after ``dopo`` (or append) and return its index."""
        nuovo = dict(ESERCIZIO_VUOTO)
        if dopo is None:
            self._esercizi.append(nuovo)
            self._dirty = True
            return len(self._esercizi) - 1
        self._esame(dopo)
        self._esercizi.insert(dopo + 1, nuovo)
        self._dirty = True
        return dopo + 1

    def rimuovi(self, indice: int) -> None:
        self._esame(indice)
        del self._esercizi[indice]
        self._dirty = True

    def sposta(self, indice: int, verso: int) -> int:
        """Swap with the neighbour (-1 su, +1 giu); returns the new index."""
        self._esame(indice)
        destinatario = indice + verso
        if destinatario < 0 or destinatario >= len(self._esercizi):
            return indice
        esercizi = self._esercizi
        esercizi[indice], esercizi[destinatario] = esercizi[destinatario], esercizi[indice]
        self._dirty = True
        return destinatario

    def gruppi_esistenti(self) -> list[str]:
        """Distinct non-empty group names, in first-appearance order."""
        visti: list[str] = []
        for esercizio in self._esercizi:
            gruppo = str(esercizio.get("gruppo") or "").strip()
            if gruppo and gruppo not in visti:
                visti.append(gruppo)
        return visti

    def duplicati_slug(self) -> dict[str, list[int]]:
        """Slug -> indices of the exercises that would collide on frame names."""
        return trova_duplicati_slug(self._esercizi)

    def importa_csv(self, percorso: str | Path, *, sostituisci: bool = False) -> int:
        """Parse a plain manifest CSV and merge it in; returns imported count.

        Frame paths are manifest-internal (bundle layout), so a bare CSV can
        only reference files that exist next to it: keep them when resolvable
        against the CSV folder, otherwise drop them for later re-extraction.
        """
        try:
            esercizi = parse_esercizi_csv(percorso)
        except ValueError as exc:
            raise EditorValidationError(f"CSV non valido: {exc}") from exc
        cartella_csv = self._path_cls(percorso).parent
        for esercizio in esercizi:
            for chiave in ("frame_start", "frame_finish"):
                valore = esercizio.get(chiave)
                if not valore:
                    continue
                risolto = cartella_csv / str(valore)
                esercizio[chiave] = str(risolto) if risolto.is_file() else None
        self.importa_esercizi(esercizi, sostituisci=sostituisci)
        return len(esercizi)

    def importa_scheda(self, percorso_bundle: str, *, sostituisci: bool = False,
                       loader=None) -> int:
        """Import exercises from another .scheda bundle (already downloaded)."""
        if loader is None:
            from core.scheda_file import carica_scheda
            loader = carica_scheda
        esercizi, _ = loader(percorso_bundle)
        self.importa_esercizi(esercizi, sostituisci=sostituisci)
        return len(esercizi)

    def importa_esercizi(self, esercizi: list[dict], *, sostituisci: bool = False) -> None:
        if sostituisci:
            self._esercizi[:] = [dict(esercizio) for esercizio in esercizi]
        else:
            self._esercizi.extend(dict(esercizio) for esercizio in esercizi)
        self._dirty = True

    def salva(self):
        """Rewrite the bundle and upload it.

        Returns the UploadResult on success, or the SyncConflict emitted by
        ``drive_sync``.  The bundle is always written locally first; the dirty
        flag is cleared only once the remote accepted the upload, so a failed
        or conflicting save keeps asking the user to retry.
        """
        for indice, esercizio in enumerate(self._esercizi):
            if not str(esercizio.get("nome") or "").strip():
                raise EditorValidationError(
                    f"L'esercizio {indice + 1} non ha un nome: completo o rimosso prima di salvare."
                )
        state_path = None
        if self._lavoro:
            candidato = self._path_cls(percorso_stato(self._lavoro))
            state_path = str(candidato) if candidato.exists() else None
        self._save_scheda(self._esercizi, self._percorso, state_path=state_path,
                          titolo=self._titolo)
        if self._upload is None:
            self._dirty = False
            return None
        risultato = self._upload(self._percorso)
        if not isinstance(risultato, SyncConflict):
            self._dirty = False
        return risultato

    @classmethod
    def da_bundle(cls, esercizi: list[dict], percorso_bundle: str, cartella_lavoro: str,
                  **iniettabili):
        """Build the editor reading the persistent title from the work dir."""
        return cls(esercizi, percorso_bundle=percorso_bundle,
                   cartella_lavoro=cartella_lavoro,
                   titolo=titolo_scheda(cartella_lavoro), **iniettabili)

    def _esame(self, indice: int) -> dict:
        try:
            return self._esercizi[indice]
        except IndexError as exc:
            raise EditorValidationError(f"Indice esercizio non valido: {indice + 1}.") from exc
