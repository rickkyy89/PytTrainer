"""Testable application behavior for the Drive-backed Kivy home."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from core.drive_sync import DriveSync, RemoteScheda
from core.scheda_file import carica_scheda, salva_scheda

from .config import AppConfigError, DriveFolderConfig, FolderConfigStore


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


class HomeUnavailableError(Exception):
    """A user-facing failure for unavailable Google Drive or invalid data."""


@dataclass(frozen=True)
class ExerciseView:
    """Read-only exercise data used by the home detail screen."""

    name: str
    explanation: str
    notes: str
    repetitions: str
    recovery: str
    group: str
    frame_start: str | None
    frame_finish: str | None


@dataclass(frozen=True)
class ReadonlyScheda:
    """Downloaded bundle data that can be safely presented without editing."""

    name: str
    local_path: Path
    exercises: tuple[ExerciseView, ...]


class DriveHomeController:
    """Coordinates configuration, authentication, Drive I/O, and bundle reading."""

    def __init__(self, config_store: FolderConfigStore, cache_dir: str | Path, *,
                 credential_provider, drive_service_factory, sync_factory=DriveSync,
                 load_scheda=carica_scheda, save_scheda=salva_scheda,
                 base_dir: str | Path | None = None):
        self._config_store = config_store
        self._cache_dir = Path(cache_dir)
        self._base_dir = Path(base_dir) if base_dir is not None else self._cache_dir.parent
        self._credential_provider = credential_provider
        self._drive_service_factory = drive_service_factory
        self._sync_factory = sync_factory
        self._load_scheda = load_scheda
        self._save_scheda = save_scheda
        self._config = config_store.load()
        self._sync = None

    @property
    def folder_config(self) -> DriveFolderConfig:
        return self._config

    @property
    def credential_provider(self):
        """Provider shared with the document generation flow (ticket 08)."""
        return self._credential_provider

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def refresh(self) -> list[RemoteScheda]:
        return self._call("aggiornare la lista delle schede", lambda: self._drive().list_schede())

    def select_folder(self, folder_id: str) -> DriveFolderConfig:
        if folder_id not in self._config.folder_ids:
            raise AppConfigError("La cartella selezionata non e configurata localmente.")
        self._config = DriveFolderConfig(self._config.folder_ids, folder_id)
        self._config_store.save(self._config)
        self._sync = None
        return self._config

    def add_folder(self, folder_id: str) -> DriveFolderConfig:
        normalized = folder_id.strip()
        if not normalized:
            raise AppConfigError("L'ID della cartella Drive non puo essere vuoto.")
        folder_ids = self._config.folder_ids
        if normalized not in folder_ids:
            folder_ids += (normalized,)
        self._config = DriveFolderConfig(folder_ids, normalized)
        self._config_store.save(self._config)
        self._sync = None
        return self._config

    def open(self, remote: RemoteScheda) -> ReadonlyScheda:
        esercizi, _, local_path = self._download_editable(remote)
        return ReadonlyScheda(
            remote.name,
            local_path,
            tuple(ExerciseView(
                exercise["nome"], exercise["spiegazione"], exercise["note"],
                exercise["ripetizioni"], exercise["recupero"], exercise.get("gruppo", ""),
                exercise.get("frame_start"), exercise.get("frame_finish"),
            ) for exercise in esercizi),
        )

    def open_for_edit(self, remote: RemoteScheda):
        """Download the bundle and return an editor over its live exercises."""
        from .editor import SchedaEditorController

        esercizi, lavoro, local_path = self._download_editable(remote)
        return SchedaEditorController.da_bundle(
            esercizi, str(local_path), lavoro,
            save_scheda=self._save_scheda,
            # Pin the upload to the opened file id: same-name bundles must not
            # cross-update each other even if the name-keyed cache collides.
            upload=lambda path: self._drive().upload_scheda(path, file_id=remote.id),
        )

    def open_for_workout(self, remote: RemoteScheda) -> list[dict]:
        """Download the bundle and return the raw exercise dicts for workout mode.

        Workout mode is read-only session state (ticket 09): no editor, no
        save path, nothing persisted back to the bundle.
        """
        esercizi, _, _ = self._download_editable(remote)
        return esercizi

    # ----------------------------------------------------- conflitti (10)

    def check_conflict(self, remote: RemoteScheda):
        """Open-time conflict check without downloading (ticket 10)."""
        def operation():
            local = self.cache_path(remote.name)
            if not local.exists():
                return None
            return self._drive().check_conflict(local, remote.id)
        return self._call("verificare i conflitti", operation)

    def cache_path(self, name: str) -> Path:
        """Absolute cache path of a bundle name (single source of truth)."""
        return self._cache_dir / name

    def resolve_conflict(self, conflict, *, choice: str, local_path: str | Path | None = None):
        """Apply one of the three user choices for a SyncConflict.

        ``local_path`` is the authoritative path of the opened bundle (the one
        the editor saves to); it is used instead of ``cache/conflict.name`` so
        a remote rename between detection and resolution cannot break the
        "locale"/"duplicata" choices. ``locale`` overwrites the remote with
        the (already saved) local bundle, ``remota`` re-downloads the remote
        discarding local edits and returns its path, ``duplicata`` uploads the
        local bundle under a new remote-unique suffixed name and then restores
        the original from the remote, so the conflict cannot loop forever.
        """
        def operation():
            drive = self._drive()
            local = Path(local_path) if local_path is not None else self.cache_path(conflict.name)
            if choice == "locale":
                return drive.upload_scheda(local, conflict.file_id, force=True)
            if choice == "remota":
                return drive.download_scheda(conflict.file_id, conflict.name)
            if choice == "duplicata":
                duplicate = self._duplicate_path(conflict.name)
                shutil.copy2(local, duplicate)
                risultato = drive.create_scheda(duplicate)
                drive.download_scheda(conflict.file_id, conflict.name)
                return risultato
            raise HomeUnavailableError(f"Scelta di conflitto sconosciuta: {choice}.")
        return self._call("risolvere il conflitto", operation)

    def _duplicate_path(self, name: str) -> Path:
        """A cache path whose ``.scheda`` name is unused both locally and remotely."""
        stem = name[: -len(".scheda")] if name.endswith(".scheda") else name
        taken = {scheda.name for scheda in self._drive().list_schede()}
        n = 2
        while True:
            candidate_name = f"{stem} ({n}).scheda"
            candidate = self._cache_dir / candidate_name
            if candidate_name not in taken and not candidate.exists():
                return candidate
            n += 1

    def import_remote_into(self, editor, remote: RemoteScheda, *, sostituisci: bool,
                           posizione: int | None = None) -> int:
        """Download another bundle and merge its exercises into the editor."""
        def operation():
            esercizi, _, _ = self._download_editable(remote)
            editor.importa_esercizi(esercizi, sostituisci=sostituisci, posizione=posizione)
            return len(esercizi)
        return self._call("importare la scheda", operation)

    def _download_editable(self, remote: RemoteScheda):
        def operation():
            local_path = self._drive().download_scheda(remote.id, remote.name)
            esercizi, lavoro = self._load_scheda(str(local_path))
            return esercizi, lavoro, local_path
        return self._call("aprire la scheda", operation)

    def create(self, name: str) -> RemoteScheda:
        filename = self._filename(name)
        local_path = self._cache_dir / filename
        def operation():
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._save_scheda([], str(local_path), titolo=Path(filename).stem)
            return self._drive().create_scheda(local_path).remote
        return self._call("creare la scheda", operation)

    def delete(self, remote: RemoteScheda) -> None:
        self._call("eliminare la scheda", lambda: self._drive().delete_scheda(remote.id))

    def _drive(self):
        if self._sync is None:
            credentials = self._credential_provider.get_credentials([DRIVE_SCOPE])
            service = self._drive_service_factory(credentials)
            self._sync = self._sync_factory(service, self._config.current_folder_id, self._cache_dir)
        return self._sync

    @staticmethod
    def _filename(name: str) -> str:
        filename = name.strip()
        if not filename:
            raise HomeUnavailableError("Inserisci un nome per la nuova scheda.")
        if not filename.endswith(".scheda"):
            filename += ".scheda"
        if Path(filename).name != filename:
            raise HomeUnavailableError("Il nome della scheda non puo contenere cartelle.")
        return filename

    @staticmethod
    def _call(action: str, operation):
        try:
            return operation()
        except HomeUnavailableError:
            raise
        except Exception as exc:
            raise HomeUnavailableError(
                f"Impossibile {action}: Drive non disponibile. Verifica la connessione e riprova."
            ) from exc
