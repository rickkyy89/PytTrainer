from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "database" / "exercises.db"

SCHEMA = r'''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, source_url)
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_url TEXT NOT NULL UNIQUE,
    original_url TEXT NOT NULL,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    duration REAL,
    description TEXT NOT NULL DEFAULT '',
    collection_id INTEGER,
    status TEXT NOT NULL DEFAULT 'NEW',
    local_path TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_platform ON videos(platform);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    subcategory TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    repetitions TEXT NOT NULL DEFAULT '',
    recovery TEXT NOT NULL DEFAULT '',
    timestamp_start REAL,
    timestamp_finish REAL,
    confidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_exercises_category ON exercises(category, subcategory);
CREATE INDEX IF NOT EXISTS idx_exercises_video ON exercises(video_id);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS exercise_tags (
    exercise_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY(exercise_id, tag_id),
    FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_tags (
    video_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY(video_id, tag_id),
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_video_tags_video ON video_tags(video_id);
'''


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: Path | str = DEFAULT_DB) -> None:
    with connect(db_path) as con:
        con.executescript(SCHEMA)


def upsert_collection(
    con: sqlite3.Connection,
    *,
    name: str,
    platform: str,
    source_url: str,
) -> int:
    con.execute(
        """
        INSERT INTO collections(name, platform, source_url)
        VALUES (?, ?, ?)
        ON CONFLICT(platform, source_url) DO UPDATE SET name=excluded.name
        """,
        (name, platform, source_url),
    )
    row = con.execute(
        "SELECT id FROM collections WHERE platform=? AND source_url=?",
        (platform, source_url),
    ).fetchone()
    return int(row["id"])


def upsert_video(
    con: sqlite3.Connection,
    *,
    canonical_url: str,
    original_url: str,
    platform: str,
    external_id: str = "",
    title: str = "",
    author: str = "",
    duration: float | None = None,
    description: str = "",
    collection_id: int | None = None,
    metadata: dict | None = None,
) -> tuple[int, bool]:
    existing = con.execute(
        "SELECT id FROM videos WHERE canonical_url=?", (canonical_url,)
    ).fetchone()

    payload = json.dumps(metadata or {}, ensure_ascii=False)
    if existing:
        con.execute(
            """
            UPDATE videos
            SET original_url=?, platform=?, external_id=?,
                title=CASE WHEN ? <> '' THEN ? ELSE title END,
                author=CASE WHEN ? <> '' THEN ? ELSE author END,
                duration=COALESCE(?, duration),
                description=CASE WHEN ? <> '' THEN ? ELSE description END,
                collection_id=COALESCE(?, collection_id),
                metadata_json=CASE WHEN ? <> '{}' THEN ? ELSE metadata_json END,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                original_url,
                platform,
                external_id,
                title, title,
                author, author,
                duration,
                description, description,
                collection_id,
                payload, payload,
                int(existing["id"]),
            ),
        )
        return int(existing["id"]), False

    cur = con.execute(
        """
        INSERT INTO videos(
            canonical_url, original_url, platform, external_id, title, author,
            duration, description, collection_id, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            canonical_url,
            original_url,
            platform,
            external_id,
            title,
            author,
            duration,
            description,
            collection_id,
            payload,
        ),
    )
    return int(cur.lastrowid), True


def list_videos(con: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return list(
            con.execute(
                "SELECT * FROM videos WHERE status=? ORDER BY id", (status,)
            ).fetchall()
        )
    return list(con.execute("SELECT * FROM videos ORDER BY id").fetchall())


def replace_exercises_for_video(
    con: sqlite3.Connection,
    video_id: int,
    exercises: Iterable[dict],
) -> None:
    con.execute("DELETE FROM exercises WHERE video_id=?", (video_id,))
    for ex in exercises:
        cur = con.execute(
            """
            INSERT INTO exercises(
                video_id, name, category, subcategory, description, notes,
                repetitions, recovery, timestamp_start, timestamp_finish, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                str(ex.get("name", "")).strip(),
                str(ex.get("category", "")).strip(),
                str(ex.get("subcategory", "")).strip(),
                str(ex.get("description", "")).strip(),
                str(ex.get("notes", "")).strip(),
                str(ex.get("repetitions", "")).strip(),
                str(ex.get("recovery", "")).strip(),
                ex.get("timestamp_start"),
                ex.get("timestamp_finish"),
                str(ex.get("confidence", "")).strip(),
            ),
        )
        exercise_id = int(cur.lastrowid)
        for tag in ex.get("tags", []) or []:
            tag = str(tag).strip()
            if not tag:
                continue
            con.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
            tag_id = con.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()["id"]
            con.execute(
                "INSERT OR IGNORE INTO exercise_tags(exercise_id, tag_id) VALUES (?, ?)",
                (exercise_id, int(tag_id)),
            )
    con.execute(
        "UPDATE videos SET status='ANALYZED', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (video_id,),
    )


def replace_video_tags(con: sqlite3.Connection, video_id: int, tags: Iterable[str]) -> None:
    con.execute("DELETE FROM video_tags WHERE video_id=?", (video_id,))
    for tag in tags:
        name = str(tag).strip()
        if not name:
            continue
        con.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
        tag_id = con.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
        con.execute(
            "INSERT OR IGNORE INTO video_tags(video_id, tag_id) VALUES (?, ?)",
            (video_id, int(tag_id)),
        )
