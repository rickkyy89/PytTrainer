"""Testable application behavior for the Drive-backed Kivy home."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
                 load_scheda=carica_scheda, save_scheda=salva_scheda):
        self._config_store = config_store
        self._cache_dir = Path(cache_dir)
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
        def operation():
            local_path = self._drive().download_scheda(remote.id, remote.name)
            exercises, _ = self._load_scheda(str(local_path))
            return ReadonlyScheda(
                remote.name,
                local_path,
                tuple(ExerciseView(
                    exercise["nome"], exercise["spiegazione"], exercise["note"],
                    exercise["ripetizioni"], exercise["recupero"], exercise.get("gruppo", ""),
                    exercise.get("frame_start"), exercise.get("frame_finish"),
                ) for exercise in exercises),
            )
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
