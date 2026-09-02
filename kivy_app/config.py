"""Persistent local configuration for the Kivy application."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FOLDER_ID = "1UthYZdR1GiVADYNUWBN1cX3z790FEkXq"


class AppConfigError(ValueError):
    """Raised when the local folder configuration is invalid."""


@dataclass(frozen=True)
class DriveFolderConfig:
    """Configured Drive folders and the folder currently shown by the home."""

    folder_ids: tuple[str, ...]
    current_folder_id: str


class FolderConfigStore:
    """JSON-backed, atomically written store for local Drive folder choices."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def load(self) -> DriveFolderConfig:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return DriveFolderConfig((DEFAULT_FOLDER_ID,), DEFAULT_FOLDER_ID)
        except (OSError, json.JSONDecodeError) as exc:
            raise AppConfigError("Impossibile leggere la configurazione delle cartelle Drive.") from exc
        try:
            folder_ids = tuple(self._folder_id(value) for value in payload["folder_ids"])
            current_folder_id = self._folder_id(payload["current_folder_id"])
        except (KeyError, TypeError, AppConfigError) as exc:
            raise AppConfigError("Configurazione delle cartelle Drive non valida.") from exc
        if not folder_ids or len(set(folder_ids)) != len(folder_ids) or current_folder_id not in folder_ids:
            raise AppConfigError("Configurazione delle cartelle Drive non valida.")
        return DriveFolderConfig(folder_ids, current_folder_id)

    def save(self, config: DriveFolderConfig) -> None:
        if not config.folder_ids or config.current_folder_id not in config.folder_ids:
            raise AppConfigError("Configurazione delle cartelle Drive non valida.")
        payload = {"folder_ids": list(config.folder_ids), "current_folder_id": config.current_folder_id}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _folder_id(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AppConfigError("L'ID della cartella Drive non puo essere vuoto.")
        return value.strip()
