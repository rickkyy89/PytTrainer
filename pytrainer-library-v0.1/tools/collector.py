from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from db import DEFAULT_DB, connect, init_db, list_videos, upsert_collection, upsert_video

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "youtu.be" in host or "youtube.com" in host:
        return "youtube"
    if "instagram.com" in host:
        return "instagram"
    if "facebook.com" in host or "fb.watch" in host:
        return "facebook"
    return "web"


def youtube_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower().endswith("youtu.be"):
        return parsed.path.strip("/").split("/")[0]
    if "youtube.com" in parsed.netloc.lower():
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        m = re.match(r"/(?:shorts|embed)/([^/?]+)", parsed.path)
        if m:
            return m.group(1)
    return ""


def canonicalize(url: str, platform: str, external_id: str = "") -> str:
    if platform == "youtube":
        vid = external_id or youtube_video_id(url)
        if vid:
            return f"https://www.youtube.com/watch?v={vid}"
    return url.strip()


def ydl_extract(url: str, *, flat: bool = False) -> dict:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp non installato. Esegui: pip install -r requirements.txt")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist" if flat else False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def add_url(url: str, db_path: Path, fetch_metadata: bool) -> tuple[int, bool]:
    platform = detect_platform(url)
    info: dict = {}
    if fetch_metadata:
        try:
            info = ydl_extract(url)
        except Exception as exc:
            print(f"[WARN] Metadata non disponibili: {exc}")

    external_id = str(info.get("id") or youtube_video_id(url) or "")
    canonical = canonicalize(url, platform, external_id)
    with connect(db_path) as con:
        return upsert_video(
            con,
            canonical_url=canonical,
            original_url=url,
            platform=platform,
            external_id=external_id,
            title=str(info.get("title") or ""),
            author=str(info.get("uploader") or info.get("channel") or ""),
            duration=float(info["duration"]) if info.get("duration") is not None else None,
            description=str(info.get("description") or ""),
            metadata=info,
        )


def import_youtube_playlist(url: str, db_path: Path) -> tuple[int, int]:
    info = ydl_extract(url, flat=True)
    collection_name = str(info.get("title") or "Playlist YouTube")
    entries = info.get("entries") or []
    new_count = 0
    existing_count = 0

    with connect(db_path) as con:
        collection_id = upsert_collection(
            con,
            name=collection_name,
            platform="youtube",
            source_url=url,
        )
        for entry in entries:
            if not entry:
                continue
            external_id = str(entry.get("id") or "")
            entry_url = str(entry.get("url") or "")
            if external_id:
                canonical = f"https://www.youtube.com/watch?v={external_id}"
            elif entry_url.startswith("http"):
                canonical = canonicalize(entry_url, "youtube")
            else:
                continue
            _, created = upsert_video(
                con,
                canonical_url=canonical,
                original_url=canonical,
                platform="youtube",
                external_id=external_id,
                title=str(entry.get("title") or ""),
                author=str(entry.get("uploader") or entry.get("channel") or ""),
                duration=float(entry["duration"]) if entry.get("duration") is not None else None,
                collection_id=collection_id,
                metadata=entry,
            )
            if created:
                new_count += 1
            else:
                existing_count += 1

    return new_count, existing_count


def print_videos(db_path: Path, status: str | None) -> None:
    with connect(db_path) as con:
        rows = list_videos(con, status)
    if not rows:
        print("Nessun video.")
        return
    for r in rows:
        title = r["title"] or "(senza titolo)"
        print(f"#{r['id']:04d} [{r['status']}] {r['platform']:<9} {title}")
        print(f"       {r['canonical_url']}")


def main() -> None:
    p = argparse.ArgumentParser(description="pyTrainer Exercise Library collector")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    a = sub.add_parser("add", help="Aggiunge un URL singolo")
    a.add_argument("url")
    a.add_argument("--metadata", action="store_true", help="Prova a leggere i metadata con yt-dlp")

    pl = sub.add_parser("playlist", help="Importa una playlist YouTube senza scaricare i video")
    pl.add_argument("url")

    ls = sub.add_parser("list", help="Elenca i video")
    ls.add_argument("--status", choices=["NEW", "DOWNLOADED", "READY_FOR_ANALYSIS", "ANALYZED", "ERROR"])

    args = p.parse_args()
    init_db(args.db)

    if args.cmd == "init":
        print(f"Database inizializzato: {args.db}")
    elif args.cmd == "add":
        video_id, created = add_url(args.url, args.db, args.metadata)
        print(f"{'Aggiunto' if created else 'Già presente'} video #{video_id}")
    elif args.cmd == "playlist":
        new_count, existing_count = import_youtube_playlist(args.url, args.db)
        print(f"Nuovi: {new_count} | già presenti: {existing_count}")
    elif args.cmd == "list":
        print_videos(args.db, args.status)


if __name__ == "__main__":
    main()
