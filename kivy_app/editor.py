"""Editor-domain behavior for one opened .scheda, free of any Kivy import.

``SchedaEditorController`` owns the mutable exercise list of an opened bundle
and the unsaved-changes flag.  Persistence is two-step: rewrite the bundle via
``core.scheda_file.salva_scheda`` (keeping frames, state and title) then upload
through an injected callable.  A ``SyncConflict`` from the upload is returned
verbatim for the UI (ticket 10 decides the resolution policy).
"""

from __future__ import annotations

from copy import deepcopy
import os
import shutil
import tempfile
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


class _SnapshotCommand:
    """Reversible manifest mutation owned by the editor history."""

    def __init__(self, target, before, after, *, files_root=None,
                 before_files=None, after_files=None):
        self._target = target
        self._before = before
        self._after = after
        self._files_root = Path(files_root) if files_root else None
        self._before_files = before_files
        self._after_files = after_files

    def undo(self):
        current = deepcopy(self._target)
        try:
            self._restore_files(self._before_files)
            self._target[:] = deepcopy(self._before)
        except Exception:
            self._target[:] = current
            raise

    def redo(self):
        current = deepcopy(self._target)
        try:
            self._restore_files(self._after_files)
            self._target[:] = deepcopy(self._after)
        except Exception:
            self._target[:] = current
            raise

    def release(self):
        self._target = None
        self._before = None
        self._after = None
        self._files_root = None
        self._before_files = None
        self._after_files = None

    def _restore_files(self, files):
        if self._files_root is None or files is None:
            return
        _restore_files_atomically(self._files_root, files)


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
        self._non_sync = False
        self._undo_stack = []
        self._redo_stack = []
        self._checkpoint = deepcopy(esercizi)
        self._checkpoint_files = self._snapshot_files(self._frames_root())

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def cronologia_dimensione(self) -> int:
        """Number of undoable editor actions currently retained."""
        return len(self._undo_stack)

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        comando = self._undo_stack[-1]
        comando.undo()
        self._undo_stack.pop()
        self._redo_stack.append(comando)
        self._dirty = self._is_dirty()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        comando = self._redo_stack[-1]
        comando.redo()
        self._redo_stack.pop()
        self._undo_stack.append(comando)
        self._dirty = self._is_dirty()
        return True

    def restore_checkpoint(self) -> None:
        """Restore the last successful local save without uploading it."""
        current = deepcopy(self._esercizi)
        try:
            _restore_files_atomically(self._frames_root(), self._checkpoint_files)
            self._esercizi[:] = deepcopy(self._checkpoint)
        except Exception:
            self._esercizi[:] = current
            raise
        self._clear_history()
        self._dirty = False

    def discard(self) -> None:
        """Discard in-memory changes; the caller may then leave the screen."""
        self.restore_checkpoint()

    def transazione_media(self, operation, *, output_dir: str | Path):
        """Run one media mutation with manifest and frame-file undo support."""
        root = Path(output_dir)
        before = self._snapshot_files(root)
        prima = deepcopy(self._esercizi)
        try:
            risultato = operation()
            if risultato is False:
                self._esercizi[:] = prima
                self._restore_files(root, before)
                return risultato
        except Exception:
            self._esercizi[:] = prima
            self._restore_files(root, before)
            raise
        dopo = deepcopy(self._esercizi)
        dopo_files = self._snapshot_files(root)
        if prima == dopo and before == dopo_files:
            return risultato
        self._registra(_SnapshotCommand(
            self._esercizi, prima, dopo, files_root=root,
            before_files=before, after_files=dopo_files))
        return risultato

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

    @property
    def non_sincronizzato(self) -> bool:
        """True when the local bundle is newer than the copy on Drive."""
        return self._non_sync

    def marca_modifica(self) -> None:
        """Flag external mutations (video & frame flow of ticket 07) as unsaved."""
        self._dirty = True

    def conferma_salvataggio(self) -> None:
        """Clear the dirty flag once an out-of-band conflict resolution synced the bundle."""
        self._dirty = False
        self._non_sync = False
        self._checkpoint = deepcopy(self._esercizi)
        self._checkpoint_files = self._snapshot_files(self._frames_root())
        self._clear_history()

    @property
    def titolo(self) -> str | None:
        return self._titolo

    def aggiorna(self, indice: int, **campi: str) -> None:
        non_locali = set(campi) - set(CAMPI_EDITABILI)
        if non_locali:
            raise EditorValidationError(f"Campo non modificabile: {sorted(non_locali)[0]}.")
        def operation():
            esercizio = self._esame(indice)
            for chiave, valore in campi.items():
                esercizio[chiave] = str(valore)

        self._modifica(operation)

    def aggiungi(self, dopo: int | None = None) -> int:
        """Insert a blank exercise after ``dopo`` (or append) and return its index."""
        indice = len(self._esercizi) if dopo is None else dopo + 1

        def operation():
            if dopo is not None:
                self._esame(dopo)
            self._esercizi.insert(indice, dict(ESERCIZIO_VUOTO))
            return indice

        return self._modifica(operation)

    def rimuovi(self, indice: int) -> None:
        self._modifica(lambda: self._esercizi.pop(self._indice_valido(indice)))

    def sposta(self, indice: int, verso: int) -> int:
        """Swap with the neighbour (-1 su, +1 giu); returns the new index."""
        destinatario = indice + verso
        self._esame(indice)
        if destinatario < 0 or destinatario >= len(self._esercizi):
            return indice

        def operation():
            self._esercizi[indice], self._esercizi[destinatario] = (
                self._esercizi[destinatario], self._esercizi[indice])
            return destinatario

        return self._modifica(operation)

    def sposta_alla(self, indice: int, destinazione: int) -> int:
        """Ricolloca l'esercizio alla posizione assoluta ``destinazione`` (0-based).

        A differenza di ``sposta`` non scambia con il vicino: estrae l'elemento
        e lo reinserisce, cosicche l'ordine relativo degli altri esercizi resta
        invariato. Ritorna l'indice finale (clampato al range valido).
        """
        self._esame(indice)
        totale = len(self._esercizi)
        if destinazione < 0 or destinazione >= totale:
            raise EditorValidationError(
                f"Posizione di destinazione non valida: {destinazione + 1} (1-{totale})."
            )
        if indice == destinazione:
            return indice
        def operation():
            esercizio = self._esercizi.pop(indice)
            self._esercizi.insert(destinazione, esercizio)
            return destinazione

        return self._modifica(operation)

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

    def importa_csv(self, percorso: str | Path, *, sostituisci: bool = False,
                    posizione: int | None = None) -> int:
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
        self.importa_esercizi(esercizi, sostituisci=sostituisci, posizione=posizione)
        return len(esercizi)

    def importa_scheda(self, percorso_bundle: str, *, sostituisci: bool = False,
                       posizione: int | None = None, loader=None) -> int:
        """Import exercises from another .scheda bundle (already downloaded)."""
        if loader is None:
            from core.scheda_file import carica_scheda
            loader = carica_scheda
        esercizi, _ = loader(percorso_bundle)
        self.importa_esercizi(esercizi, sostituisci=sostituisci, posizione=posizione)
        return len(esercizi)

    def importa_esercizi(self, esercizi: list[dict], *, sostituisci: bool = False,
                         posizione: int | None = None) -> None:
        def operation():
            if sostituisci:
                self._esercizi[:] = [dict(esercizio) for esercizio in esercizi]
            elif posizione is None:
                self._esercizi.extend(dict(esercizio) for esercizio in esercizi)
            else:
                if posizione < 0 or posizione > len(self._esercizi):
                    raise EditorValidationError(
                        f"Posizione di inserimento non valida: {posizione + 1} "
                        f"(1-{len(self._esercizi) + 1})."
                    )
                for offset, esercizio in enumerate(esercizi):
                    self._esercizi.insert(posizione + offset, dict(esercizio))

        self._modifica(operation)

    def salva(self, sincronizza: bool = True):
        """Rewrite the bundle and (optionally) upload it.

        Returns the UploadResult on success, or the SyncConflict emitted by
        ``drive_sync``.  The bundle is always written locally first; the dirty
        flag is cleared only once the remote accepted the upload, so a failed
        or conflicting save keeps asking the user to retry.

        With ``sincronizza=False`` the bundle is saved only on disk: the local
        copy stays flagged as ``non_sincronizzato`` until the next real sync.
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
        self._checkpoint = deepcopy(self._esercizi)
        self._checkpoint_files = self._snapshot_files(self._frames_root())
        self._clear_history()
        self._dirty = False
        if not sincronizza:
            self._non_sync = True
            return None
        if self._upload is None:
            self._non_sync = False
            return None
        try:
            risultato = self._upload(self._percorso)
        except Exception:
            self._non_sync = True
            raise
        if isinstance(risultato, SyncConflict):
            self._non_sync = True
        else:
            self._non_sync = False
        return risultato

    def salva_locale(self):
        """Create a local checkpoint and leave Drive untouched."""
        return self.salva(sincronizza=False)

    def salva_drive(self):
        """Create a local checkpoint, then upload it to Drive."""
        return self.salva(sincronizza=True)

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

    def _indice_valido(self, indice: int) -> int:
        self._esame(indice)
        return indice

    def _modifica(self, operation):
        """Run one editor mutation and record it as one reversible action."""
        prima = deepcopy(self._esercizi)
        try:
            risultato = operation()
        except Exception:
            self._esercizi[:] = prima
            raise
        dopo = deepcopy(self._esercizi)
        if prima == dopo:
            return risultato
        self._registra(_SnapshotCommand(self._esercizi, prima, dopo))
        return risultato

    def _registra(self, comando):
        for vecchio in self._redo_stack:
            vecchio.release()
        self._redo_stack.clear()
        self._undo_stack.append(comando)
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0).release()
        self._dirty = True

    @staticmethod
    def _snapshot_files(root):
        if root is None or not root.exists():
            return {}
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and not path.name.startswith("_")
        }

    @staticmethod
    def _restore_files(root, files):
        _restore_files_atomically(root, files)

    def _frames_root(self):
        if not self._lavoro:
            return None
        return Path(self._lavoro) / "frames"

    def _is_dirty(self):
        return (self._esercizi != self._checkpoint or
                self._snapshot_files(self._frames_root()) != self._checkpoint_files)

    def _clear_history(self):
        for comando in self._undo_stack:
            comando.release()
        for comando in self._redo_stack:
            comando.release()
        self._undo_stack.clear()
        self._redo_stack.clear()


def _restore_files_atomically(root, files):
    """Replace managed frame files and restore them if a write fails."""
    if root is None:
        return
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    current = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith("_")
    }
    staging = Path(tempfile.mkdtemp(prefix=".history-", dir=str(root.parent)))
    try:
        for relative, content in files.items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        for relative in current:
            (root / relative).unlink()
        for relative in files:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, destination)
    except Exception:
        for path in root.rglob("*"):
            if path.is_file() and not path.name.startswith("_"):
                path.unlink()
        for relative, content in current.items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
