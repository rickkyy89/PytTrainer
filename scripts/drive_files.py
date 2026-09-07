"""Upload and download CSV or .scheda files from the configured Drive folder."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.platform import LocalCredentialsProvider  # noqa: E402
from kivy_app.config import DEFAULT_FOLDER_ID  # noqa: E402
from kivy_app.controller import DRIVE_SCOPE  # noqa: E402


ALLOWED_TYPES = {
    ".csv": "text/csv",
    ".scheda": "application/zip",
    ".apk": "application/vnd.android.package-archive",
}
FILE_FIELDS = "id,name,mimeType,modifiedTime,size,md5Checksum,webViewLink,parents"


class DriveFilesError(RuntimeError):
    """A user-facing failure while transferring a supported Drive file."""


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _validate_name(name: str) -> str:
    if Path(name).name != name or Path(name).suffix.lower() not in ALLOWED_TYPES:
        raise DriveFilesError(
            "Sono supportati solo nomi semplici con estensione .csv, .scheda o .apk."
        )
    return name


def list_files(service, folder_id: str, kind: str = "all") -> list[dict]:
    """Return supported files in one Drive folder, ordered by name."""
    files = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{_escape_query(folder_id)}' in parents and trashed = false",
            spaces="drive",
            fields=f"nextPageToken,files({FILE_FIELDS})",
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    suffix = None if kind == "all" else f".{kind}"
    supported = [
        item for item in files
        if Path(item.get("name", "")).suffix.lower() in ALLOWED_TYPES
        and (suffix is None or Path(item["name"]).suffix.lower() == suffix)
    ]
    return sorted(supported, key=lambda item: (item["name"].casefold(), item["id"]))


def _find_by_name(service, folder_id: str, name: str) -> dict | None:
    matches = [item for item in list_files(service, folder_id) if item["name"] == name]
    if len(matches) > 1:
        raise DriveFilesError(
            f"Drive contiene {len(matches)} file chiamati {name!r}; usa --file-id per scegliere quello da aggiornare."
        )
    return matches[0] if matches else None


def _get_in_folder(service, folder_id: str, file_id: str) -> dict:
    metadata = service.files().get(
        fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True
    ).execute()
    if folder_id not in metadata.get("parents", []):
        raise DriveFilesError("Il file indicato non appartiene alla cartella Drive configurata.")
    return metadata


def upload_file(
    service,
    folder_id: str,
    local_path: str | os.PathLike,
    *,
    remote_name: str | None = None,
    file_id: str | None = None,
) -> tuple[dict, bool]:
    """Create or update a supported file. Return metadata and whether it was created."""
    path = Path(local_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in ALLOWED_TYPES:
        raise DriveFilesError("Il percorso locale deve indicare un file .csv o .scheda esistente.")
    name = _validate_name(remote_name or path.name)
    if Path(name).suffix.lower() != path.suffix.lower():
        raise DriveFilesError("Il nome remoto deve mantenere l'estensione del file locale.")
    target = _get_in_folder(service, folder_id, file_id) if file_id else _find_by_name(service, folder_id, name)
    media = MediaFileUpload(str(path), mimetype=ALLOWED_TYPES[path.suffix.lower()], resumable=True)

    if target:
        result = service.files().update(
            fileId=target["id"],
            body={"name": name},
            media_body=media,
            fields=FILE_FIELDS,
            supportsAllDrives=True,
        ).execute()
        return result, False

    result = service.files().create(
        body={"name": name, "parents": [folder_id]},
        media_body=media,
        fields=FILE_FIELDS,
        supportsAllDrives=True,
    ).execute()
    return result, True


def download_file(
    service,
    folder_id: str,
    remote: str,
    *,
    output: str | os.PathLike | None = None,
    by_id: bool = False,
    force: bool = False,
) -> tuple[dict, Path]:
    """Download one supported file by exact name or Drive file ID."""
    if by_id:
        metadata = _get_in_folder(service, folder_id, remote)
    else:
        name = _validate_name(remote)
        metadata = _find_by_name(service, folder_id, name)
        if metadata is None:
            raise DriveFilesError(f"Nessun file chiamato {name!r} nella cartella Drive.")

    name = _validate_name(metadata.get("name", ""))
    destination = Path(output or name).expanduser().resolve()
    if destination.exists() and not force:
        raise DriveFilesError(f"Il file locale esiste gia: {destination}. Usa --force per sostituirlo.")
    if not destination.parent.is_dir():
        raise DriveFilesError(f"La cartella di destinazione non esiste: {destination.parent}")

    temporary = destination.with_name(f".{destination.name}.download")
    request = service.files().get_media(fileId=metadata["id"], supportsAllDrives=True)
    try:
        with temporary.open("wb") as stream:
            downloader = MediaIoBaseDownload(stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return metadata, destination


def _service(base_dir: Path):
    credentials = LocalCredentialsProvider(base_dir).get_credentials([DRIVE_SCOPE])
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder-id", default=DEFAULT_FOLDER_ID, help="ID cartella Drive")
    parser.add_argument("--base-dir", type=Path, default=ROOT, help="Cartella di credentials.json/token.json")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="Elenca CSV e schede remote")
    listing.add_argument("--kind", choices=("all", "csv", "scheda"), default="all")

    upload = commands.add_parser("upload", help="Crea o aggiorna un file remoto")
    upload.add_argument("path", type=Path)
    upload.add_argument("--name", help="Nome remoto; per default usa il nome locale")
    upload.add_argument("--file-id", help="Aggiorna questo file anziche cercarlo per nome")

    download = commands.add_parser("download", help="Scarica un file remoto")
    download.add_argument("remote", help="Nome remoto esatto, oppure ID con --file-id")
    download.add_argument("--file-id", action="store_true", help="Interpreta REMOTE come ID Drive")
    download.add_argument("--output", type=Path, help="Percorso locale di destinazione")
    download.add_argument("--force", action="store_true", help="Sostituisci il file locale se esiste")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        service = _service(args.base_dir.expanduser().resolve())
        if args.command == "list":
            files = list_files(service, args.folder_id, args.kind)
            for item in files:
                print(f"{item['id']}\t{item['name']}\t{item.get('modifiedTime', '')}")
            print(f"Totale: {len(files)}")
        elif args.command == "upload":
            item, created = upload_file(
                service, args.folder_id, args.path, remote_name=args.name, file_id=args.file_id
            )
            action = "Creato" if created else "Aggiornato"
            print(f"{action}: {item['name']} ({item['id']})")
            print(item.get("webViewLink", f"https://drive.google.com/file/d/{item['id']}/view"))
        else:
            item, destination = download_file(
                service,
                args.folder_id,
                args.remote,
                output=args.output,
                by_id=args.file_id,
                force=args.force,
            )
            print(f"Scaricato: {item['name']} -> {destination}")
    except Exception as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
