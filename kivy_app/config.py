"""Persistent local configuration for the Kivy application."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FOLDER_ID = "1UthYZdR1GiVADYNUWBN1cX3z790FEkXq"

DESTINAZIONI_LOCALI = ("documenti", "download")


class AppConfigError(ValueError):
    """Raised when the local folder configuration is invalid."""


@dataclass(frozen=True)
class DriveFolderConfig:
    """Configured Drive folders and the folder currently shown by the home."""

    folder_ids: tuple[str, ...]
    current_folder_id: str
    # Tuple instead of a mutable mapping keeps the frozen value predictable and
    # permits old two-field construction sites to remain source compatible.
    folder_names: tuple[tuple[str, str], ...] = ()

    def name_for(self, folder_id: str) -> str | None:
        return dict(self.folder_names).get(folder_id)


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
        raw_names = payload.get("folder_names", {}) if isinstance(payload, dict) else {}
        names = tuple(
            (folder_id, str(raw_names[folder_id]).strip())
            for folder_id in folder_ids
            if isinstance(raw_names, dict) and str(raw_names.get(folder_id, "")).strip()
        )
        return DriveFolderConfig(folder_ids, current_folder_id, names)

    def save(self, config: DriveFolderConfig) -> None:
        if not config.folder_ids or config.current_folder_id not in config.folder_ids:
            raise AppConfigError("Configurazione delle cartelle Drive non valida.")
        payload = {
            "folder_ids": list(config.folder_ids),
            "current_folder_id": config.current_folder_id,
            "folder_names": dict(config.folder_names),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _folder_id(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AppConfigError("L'ID della cartella Drive non puo essere vuoto.")
        return value.strip()


@dataclass(frozen=True)
class LocalPrefs:
    """Dove l'app copia i bundle affinche siano ritrovabili dall'utente."""

    destinazione: str = "documenti"


class LocalPrefsStore:
    """JSON-backed store for the local save destination (Documents/Download).

    Never raises for a missing or corrupt file: the destination is only a
    convenience, so a bad read falls back to the default rather than blocking
    the whole home screen.
    """

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def load(self) -> LocalPrefs:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return LocalPrefs()
        destinazione = payload.get("destinazione") if isinstance(payload, dict) else None
        if destinazione not in DESTINAZIONI_LOCALI:
            return LocalPrefs()
        return LocalPrefs(destinazione)

    def save(self, prefs: LocalPrefs) -> None:
        if prefs.destinazione not in DESTINAZIONI_LOCALI:
            raise AppConfigError("Destinazione di salvataggio locale non valida.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps({"destinazione": prefs.destinazione}, indent=2),
                             encoding="utf-8")
        os.replace(temporary, self.path)
