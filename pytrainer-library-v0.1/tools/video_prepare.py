from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

from db import DEFAULT_DB, ROOT, connect, init_db

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


YOUTUBE_VIDEOS = ROOT / "videos" / "youtube"


class VideoPrepareError(RuntimeError):
    """The requested video could not be prepared for analysis."""


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:80] or "untitled"


def local_path_for_database(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def is_valid_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def mark_video(
    video_id: int,
    status: str,
    db_path: Path,
    local_path: str | None = None,
) -> None:
    with connect(db_path) as con:
        if local_path is None:
            con.execute(
                "UPDATE videos SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, video_id),
            )
        else:
            con.execute(
                """
                UPDATE videos
                SET status=?, local_path=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (status, local_path, video_id),
            )


def get_video(video_id: int, db_path: Path) -> dict[str, Any]:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    if row is None:
        raise VideoPrepareError(f"Video #{video_id} non trovato")
    return dict(row)


def downloaded_file(output_dir: Path, filename_prefix: str) -> Path | None:
    candidates = [
        path for path in output_dir.glob(f"{filename_prefix}.*")
        if path.suffix != ".part" and is_valid_file(path)
    ]
    if not candidates:
        return None
    return next((path for path in candidates if path.suffix.lower() == ".mp4"), candidates[0])


def prepare_video(
    video_id: int,
    db_path: Path = DEFAULT_DB,
    output_dir: Path = YOUTUBE_VIDEOS,
    force: bool = False,
    ydl_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> Path:
    """Download one YouTube video at an analysis-friendly maximum of 720p."""
    video = get_video(video_id, db_path)
    existing_path = Path(video["local_path"]) if video["local_path"] else None
    if existing_path and not existing_path.is_absolute():
        existing_path = ROOT / existing_path
    if existing_path and is_valid_file(existing_path) and not force:
        if video["status"] != "ANALYZED":
            mark_video(video_id, "READY_FOR_ANALYSIS", db_path, local_path_for_database(existing_path))
        return existing_path

    if video["platform"] != "youtube":
        mark_video(video_id, "ERROR", db_path)
        raise VideoPrepareError(f"Video #{video_id}: piattaforma non supportata ({video['platform']})")
    if yt_dlp is None and ydl_factory is None:
        mark_video(video_id, "ERROR", db_path)
        raise VideoPrepareError("yt-dlp non installato. Esegui: pip install -r requirements.txt")

    output_dir.mkdir(parents=True, exist_ok=True)
    filename_prefix = f"{video_id:04d}_{slugify(video['title'])}"
    output_template = str(output_dir / f"{filename_prefix}.%(ext)s")
    options = {
        "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    factory = ydl_factory or yt_dlp.YoutubeDL
    try:
        with factory(options) as ydl:
            ydl.download([video["canonical_url"]])
        path = downloaded_file(output_dir, filename_prefix)
        if path is None:
            raise VideoPrepareError("yt-dlp non ha prodotto un file video valido")
    except Exception as exc:
        mark_video(video_id, "ERROR", db_path)
        if isinstance(exc, VideoPrepareError):
            raise
        raise VideoPrepareError(f"Video #{video_id}: download non riuscito: {exc}") from exc

    mark_video(video_id, "READY_FOR_ANALYSIS", db_path, local_path_for_database(path))
    return path


def discard_local_video(video_id: int, db_path: Path = DEFAULT_DB) -> Path | None:
    """Remove a downloaded source after analysis while preserving its database record."""
    video = get_video(video_id, db_path)
    path = Path(video["local_path"]) if video["local_path"] else None
    if path and not path.is_absolute():
        path = ROOT / path
    if path and path.is_file():
        path.unlink()
    next_status = "ANALYZED" if video["status"] == "ANALYZED" else "NEW"
    mark_video(video_id, next_status, db_path, "")
    return path


def print_ready_videos(db_path: Path) -> None:
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT id, title, local_path FROM videos WHERE status='READY_FOR_ANALYSIS' ORDER BY id"
        ).fetchall()
    if not rows:
        print("Nessun video pronto per l'analisi.")
        return
    for row in rows:
        print(f"#{row['id']:04d} {row['title'] or '(senza titolo)'}")
        print(f"       {row['local_path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara video YouTube per l'analisi AI")
    parser.add_argument("video_ids", nargs="*", type=int, help="ID dei video da preparare")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--force", action="store_true", help="Riscarica anche un file locale valido")
    parser.add_argument("--discard", action="store_true", help="Elimina i download locali degli ID indicati")
    parser.add_argument("--list-ready", action="store_true", help="Elenca i video pronti per l'analisi")
    args = parser.parse_args()

    init_db(args.db)
    if args.list_ready:
        if args.video_ids:
            parser.error("--list-ready non accetta ID video")
        print_ready_videos(args.db)
        return
    if not args.video_ids:
        parser.error("specifica almeno un ID video oppure --list-ready")

    if args.discard:
        for video_id in args.video_ids:
            path = discard_local_video(video_id, args.db)
            print(f"Video #{video_id}: download rimosso ({path or 'nessun file locale'})")
        return

    failures = 0
    for video_id in args.video_ids:
        try:
            path = prepare_video(video_id, args.db, force=args.force)
            print(f"Video #{video_id} pronto: {path}")
        except VideoPrepareError as exc:
            failures += 1
            print(f"[ERROR] {exc}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
