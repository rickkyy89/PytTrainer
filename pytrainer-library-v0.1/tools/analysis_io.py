from __future__ import annotations

import argparse
import json
from pathlib import Path

from db import DEFAULT_DB, connect, init_db, replace_exercises_for_video, replace_video_tags
from tag_policy import normalize_tags

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "analysis" / "pending"
RESULTS = ROOT / "analysis" / "results"


def validate_result(payload: dict, db_path: Path) -> list[dict]:
    try:
        video_id = int(payload["video_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Il risultato deve contenere un video_id intero") from exc
    exercises = payload.get("exercises")
    if not isinstance(exercises, list):
        raise ValueError("exercises deve essere una lista")
    with connect(db_path) as con:
        video = con.execute("SELECT duration FROM videos WHERE id=?", (video_id,)).fetchone()
    if video is None:
        raise ValueError(f"Video #{video_id} non trovato")
    duration = float(video["duration"] or 0)
    validated: list[dict] = []
    for index, exercise in enumerate(exercises, start=1):
        if not isinstance(exercise, dict):
            raise ValueError(f"Esercizio #{index} non e' un oggetto")
        name = str(exercise.get("name", "")).strip()
        if not name:
            raise ValueError(f"Esercizio #{index} senza nome")
        start = exercise.get("timestamp_start")
        finish = exercise.get("timestamp_finish")
        if start is not None:
            start = float(start)
        if finish is not None:
            finish = float(finish)
        if start is not None and start < 0 or finish is not None and finish < 0:
            raise ValueError(f"Esercizio #{index}: timestamp negativo")
        if start is not None and finish is not None and finish <= start:
            raise ValueError(f"Esercizio #{index}: finish deve essere maggiore di start")
        if duration and any(value is not None and value > duration + 2 for value in (start, finish)):
            raise ValueError(f"Esercizio #{index}: timestamp oltre la durata del video")
        confidence = float(exercise.get("confidence", 0))
        if not 0 <= confidence <= 1:
            raise ValueError(f"Esercizio #{index}: confidence deve essere tra 0 e 1")
        tags = exercise.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError(f"Esercizio #{index}: tags deve essere una lista")
        validated.append({
            "name": name,
            "description": str(exercise.get("description", "")).strip(),
            "notes": str(exercise.get("notes", "")).strip(),
            "category": str(exercise.get("category", "")).strip(),
            "subcategory": str(exercise.get("subcategory", "")).strip(),
            "repetitions": str(exercise.get("repetitions", "")).strip(),
            "recovery": str(exercise.get("recovery", "")).strip(),
            "timestamp_start": start,
            "timestamp_finish": finish,
            "confidence": confidence,
            "tags": normalize_tags(
                tags,
                category=str(exercise.get("category", "")),
                subcategory=str(exercise.get("subcategory", "")),
            ),
        })
    return validated


def validate_video_tags(payload: dict) -> list[str]:
    tags = payload.get("video_tags", [])
    if not isinstance(tags, list):
        raise ValueError("video_tags deve essere una lista")
    return normalize_tags(tags)


def queue_video(video_id: int, db_path: Path) -> Path:
    PENDING.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if row is None:
            raise SystemExit(f"Video #{video_id} non trovato")

    payload = {
        "video_id": int(row["id"]),
        "url": row["canonical_url"],
        "platform": row["platform"],
        "title": row["title"],
        "author": row["author"],
        "duration": row["duration"],
        "local_path": row["local_path"],
        "expected_output": {
            "exercises": [
                {
                    "name": "",
                    "category": "",
                    "subcategory": "",
                    "description": "",
                    "notes": "",
                    "repetitions": "",
                    "recovery": "",
                    "timestamp_start": None,
                    "timestamp_finish": None,
                    "confidence": "HIGH|MEDIUM|LOW",
                    "tags": [],
                }
            ]
        },
    }
    path = PENDING / f"video_{video_id:04d}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def import_result(path: Path, db_path: Path) -> None:
    init_db(db_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    video_id = int(payload["video_id"])
    exercises = validate_result(payload, db_path)
    video_tags = validate_video_tags(payload)
    with connect(db_path) as con:
        replace_exercises_for_video(con, video_id, exercises)
        replace_video_tags(con, video_id, video_tags)
    RESULTS.mkdir(parents=True, exist_ok=True)
    target = RESULTS / path.name
    if path.resolve() != target.resolve():
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Importati {len(exercises)} esercizi dal video #{video_id}")


def main() -> None:
    p = argparse.ArgumentParser(description="Bridge tra libreria e analisi AI")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("queue")
    q.add_argument("video_id", type=int)

    i = sub.add_parser("import")
    i.add_argument("json_file", type=Path)

    args = p.parse_args()
    if args.cmd == "queue":
        print(queue_video(args.video_id, args.db))
    elif args.cmd == "import":
        import_result(args.json_file, args.db)


if __name__ == "__main__":
    main()
