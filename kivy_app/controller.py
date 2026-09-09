"""Testable application behavior for the Drive-backed Kivy home."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import time

from core.drive_sync import DriveSync, RemoteScheda
from core.scheda_file import carica_scheda, salva_scheda
from core.google_retry import transient

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
                  base_dir: str | Path | None = None, local_store=None, prefs_store=None,
                  retry_sleep=None):
        self._config_store = config_store
        self._cache_dir = Path(cache_dir)
        self._base_dir = Path(base_dir) if base_dir is not None else self._cache_dir.parent
        self._credential_provider = credential_provider
        self._drive_service_factory = drive_service_factory
        self._sync_factory = sync_factory
        self._load_scheda = load_scheda
        self._save_scheda = save_scheda
        self._local_store = local_store
        self._prefs_store = prefs_store
        self._retry_sleep = retry_sleep or time.sleep
        self._config = config_store.load()
        self._sync = None
        self.avvertenza: str | None = None

    @property
    def local_store(self):
        """Visible local mirror (Android) or None (PC uses the save dialog)."""
        return self._local_store

    @property
    def destinazione_locale(self) -> str:
        """'documenti' or 'download' where local mirrors are written (Android)."""
        if self._prefs_store is None:
            return "documenti"
        return self._prefs_store.load().destinazione

    def imposta_destinazione_locale(self, kind: str) -> None:
        """Persist and apply the local mirror destination (Android only)."""
        from .config import LocalPrefs

        if self._prefs_store is not None:
            self._prefs_store.save(LocalPrefs(kind))
        if self._local_store is not None:
            self._local_store.set_kind(kind)

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
        return self._call("aggiornare la lista delle schede", lambda: self._drive().list_schede(), safe=True)

    def list_csv(self) -> list[RemoteScheda]:
        """List plain manifest CSVs stored in the configured Drive folder."""
        return self._call("elencare i CSV su Drive", lambda: self._drive().list_remote(".csv"), safe=True)

    def download_csv(self, remote: RemoteScheda) -> Path:
        """Download a CSV manifest to the cache and return its local path."""
        return self._call(
            "scaricare il CSV da Drive",
            lambda: self._drive().download_file(remote.id, remote.name),
        )

    def salva_csv_esempio(self) -> str:
        """Write the AI example CSV where the user can find it, return its label.

        On Android the mirror is always ``Download/pyTrainer`` (independent of
        the configured save destination); on PC the file lands in the user's
        ``Downloads`` folder.  Failures surface as-is: this is a local write,
        Drive is not involved.
        """
        from .ai_csv import NOME_CSV_ESEMPIO, csv_esempio

        if self._local_store is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            sorgente = self._cache_dir / NOME_CSV_ESEMPIO
            sorgente.write_text(csv_esempio(), encoding="utf-8")
            self._local_store.salva(sorgente, NOME_CSV_ESEMPIO, kind="download")
            return f"Download/pyTrainer/{NOME_CSV_ESEMPIO}"
        dest_dir = Path.home() / "Downloads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / NOME_CSV_ESEMPIO).write_text(csv_esempio(), encoding="utf-8")
        return str(dest_dir / NOME_CSV_ESEMPIO)

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
            local_store=self._local_store,
            # Pin the upload to the opened file id: same-name bundles must not
            # cross-update each other even if the name-keyed cache collides.
            upload=lambda path: self._drive().upload_scheda(path, file_id=remote.id),
        )

    def open_for_edit_locale(self, percorso: str):
        """Return an editor over a bundle chosen from the device, not from Drive.

        The editor has no Drive counterpart yet (``upload`` stays unset), so a
        later save must go through :meth:`pubblica_in_drive`, which asks the UI
        to resolve a same-name collision.
        """
        from .editor import SchedaEditorController

        finale = self._importa_locale(percorso)
        esercizi, lavoro = self._load_scheda(str(finale))
        return SchedaEditorController.da_bundle(
            esercizi, str(finale), lavoro,
            save_scheda=self._save_scheda,
            local_store=self._local_store,
        )

    def remoto_con_nome(self, nome: str) -> RemoteScheda | None:
        """The Drive file whose name matches ``nome`` (with or without extension)."""
        target = self._filename(nome).casefold()
        def operation():
            matches = [r for r in self._drive().list_schede() if r.name.casefold() == target]
            return matches[0] if matches else None
        return self._call("cercare la scheda su Drive", operation)

    def pubblica_in_drive(self, editor, *, remoto: RemoteScheda | None = None):
        """Write the bundle, then create-or-overwrite it on Drive and bind it.

        ``remoto`` is the same-name file the UI already confirmed to overwrite
        (``force`` upload); ``None`` creates a new bundle. On success the editor
        is pinned to the resulting file id so later saves are plain updates.
        """
        captured: dict[str, str] = {}

        def upload(path):
            drive = self._drive()
            if remoto is not None:
                risultato = drive.upload_scheda(path, remoto.id, force=True)
            else:
                risultato = drive.create_scheda(path)
            captured["id"] = risultato.remote.id
            return risultato

        def operation():
            risultato = editor.pubblica(upload)
            if "id" in captured:
                file_id = captured["id"]
                editor.aggancia_drive(
                    lambda p, fid=file_id: self._drive().upload_scheda(p, file_id=fid))
            return risultato
        return self._call("pubblicare la scheda su Drive", operation)

    def _importa_locale(self, percorso: str) -> Path:
        """Return a cache path for a device file (content:// copied in on Android)."""
        if self._local_store is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            return Path(self._local_store.importa(percorso, self._cache_dir))
        path = Path(percorso)
        if not path.is_file():
            raise HomeUnavailableError(f"File non trovato: {percorso}")
        return path

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

    def _duplicate_path(self, name: str, *, start: int = 2) -> Path:
        """A cache path whose ``.scheda`` name is unused both locally and remotely.

        ``start`` is the first suffix counter tried: the conflict flow uses
        the default ``2`` (never reuses the original name), while the
        duplicate flow passes ``1`` so the user-requested name is kept
        verbatim and only suffixed when it is already taken.
        """
        stem = name[: -len(".scheda")] if name.endswith(".scheda") else name
        taken = {scheda.name for scheda in self._drive().list_schede()}
        n = start
        while True:
            candidate_name = f"{stem}.scheda" if n == 1 else f"{stem} ({n}).scheda"
            candidate = self._cache_dir / candidate_name
            if candidate_name not in taken and not candidate.exists():
                return candidate
            n += 1

    def import_remote_into(self, editor, remote: RemoteScheda, *, sostituisci: bool,
                           posizione: int | None = None,
                           indici: set[int] | None = None) -> int:
        """Download another bundle and merge its exercises into the editor.

        ``indici`` selects only some exercises (by position in the remote
        bundle); ``None`` imports all of them.
        """
        def operation():
            esercizi, _, _ = self._download_editable(remote)
            self.avvertenza = None
            if indici is not None:
                esercizi = [es for i, es in enumerate(esercizi) if i in indici]
            editor.importa_esercizi(esercizi, sostituisci=sostituisci, posizione=posizione)
            return len(esercizi)
        return self._call("importare la scheda", operation)

    def _download_editable(self, remote: RemoteScheda):
        def operation():
            local_path = self.cache_path(remote.name)
            drive = self._drive()
            if drive.local_ahead(local_path, remote.id):
                self.avvertenza = ("Copia locale più recente di Drive (upload non riuscito): "
                                   "aperta senza scaricare.")
            else:
                self.avvertenza = None
                local_path = drive.download_scheda(remote.id, remote.name)
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

    def duplicate(self, remote: RemoteScheda, new_name: str) -> RemoteScheda:
        """Clone a remote bundle into a new, uniquely-named file on Drive.

        The remote copy is downloaded first, but a cached bundle with unsynced
        local edits is never clobbered: it is duplicated as-is and the reason
        is surfaced through ``avvertenza`` (same contract as ``_download_editable``).
        The requested name is used verbatim when free; otherwise
        ``_duplicate_path`` bumps a suffix so neither the cache folder nor
        Drive already holds it, then the copy is created as a new remote file.
        """
        filename = self._filename(new_name)
        def operation():
            drive = self._drive()
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            source = self.cache_path(remote.name)
            if drive.local_ahead(source, remote.id):
                self.avvertenza = ("Copia locale più recente di Drive (upload non riuscito): "
                                   "duplicata da locale senza scaricare.")
            else:
                self.avvertenza = None
                source = drive.download_scheda(remote.id, remote.name)
            duplicate = self._duplicate_path(filename, start=1)
            shutil.copy2(source, duplicate)
            return drive.create_scheda(duplicate).remote
        return self._call("duplicare la scheda", operation)

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

    def _call(self, action: str, operation, *, safe=False):
        refreshed = False
        for attempt in range(3):
            try:
                return operation()
            except HomeUnavailableError:
                raise
            except Exception as exc:
                # Never replay a workflow containing create/upload after an
                # error: an earlier write in that workflow may have succeeded.
                if safe and attempt < 2 and not getattr(exc, "google_read_retries_exhausted", False):
                    if not refreshed and self._errore_di_autenticazione(exc) and self._riautentica():
                        refreshed = True
                        self._sync = None
                        continue
                    if transient(exc) or isinstance(exc, OSError):
                        self._retry_sleep(0.5 * 2 ** attempt)
                        continue
                raise HomeUnavailableError(
                    f"Impossibile {action}: Drive non disponibile. Verifica la connessione e riprova."
                ) from exc

    @staticmethod
    def _errore_di_autenticazione(exc: Exception) -> bool:
        if type(exc).__name__ in ("CredentialProviderError", "RefreshError", "GoogleAuthError"):
            return True
        status = getattr(getattr(exc, "resp", None), "status", None)
        return status == 401

    def _riautentica(self) -> bool:
        """Ask the credential provider for a silent re-authorization (Android only)."""
        riautentica = getattr(self._credential_provider, "riautentica", None)
        if riautentica is None:
            return False
        try:
            return bool(riautentica())
        except Exception:
            return False
