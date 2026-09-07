from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from db import DEFAULT_DB, connect

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
HEADERS = [
    "Nome", "Spiegazione", "Note", "Ripetizioni", "Recupero", "Gruppo",
    "VideoURL", "TimestampStart", "TimestampFinish", "FrameStartPath", "FrameFinishPath"
]


def safe_name(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9àèéìòù]+", "_", text, flags=re.IGNORECASE)
    return text.strip("_") or "export"


def export(
    category: str | None,
    subcategory: str | None,
    output: Path | None,
    db_path: Path,
    video_ids: list[int] | None = None,
    exercise_ids: list[int] | None = None,
) -> Path:
    sql = """
        SELECT e.*, v.canonical_url
        FROM exercises e
        JOIN videos v ON v.id=e.video_id
        WHERE 1=1
    """
    params: list[str] = []
    if category:
        sql += " AND e.category = ?"
        params.append(category)
    if subcategory:
        sql += " AND e.subcategory = ?"
        params.append(subcategory)
    if video_ids:
        sql += " AND e.video_id IN (" + ", ".join("?" for _ in video_ids) + ")"
        params.extend(str(video_id) for video_id in video_ids)
    if exercise_ids:
        sql += " AND e.id IN (" + ", ".join("?" for _ in exercise_ids) + ")"
        params.extend(str(exercise_id) for exercise_id in exercise_ids)
    sql += " ORDER BY e.category, e.subcategory, e.id"

    with connect(db_path) as con:
        rows = con.execute(sql, params).fetchall()

    EXPORTS.mkdir(parents=True, exist_ok=True)
    if output is None:
        parts = [p for p in [category, subcategory] if p]
        output = EXPORTS / f"{safe_name('_'.join(parts) if parts else 'tutti')}.csv"

    with output.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        for r in rows:
            gruppo = " / ".join(p for p in [r["category"], r["subcategory"]] if p)
            w.writerow({
                "Nome": r["name"],
                "Spiegazione": r["description"],
                "Note": r["notes"],
                "Ripetizioni": r["repetitions"],
                "Recupero": r["recovery"],
                "Gruppo": gruppo,
                "VideoURL": r["canonical_url"],
                "TimestampStart": "" if r["timestamp_start"] is None else r["timestamp_start"],
                "TimestampFinish": "" if r["timestamp_finish"] is None else r["timestamp_finish"],
                "FrameStartPath": "",
                "FrameFinishPath": "",
            })
    print(f"Esportati {len(rows)} esercizi -> {output}")
    return output


def main() -> None:
    p = argparse.ArgumentParser(description="Esporta CSV compatibile con pyTrainer")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--category")
    p.add_argument("--subcategory")
    p.add_argument("--output", type=Path)
    p.add_argument("--video-id", type=int, action="append", help="Esporta solo gli esercizi di questo video")
    p.add_argument("--exercise-id", type=int, action="append", help="Esporta solo questo esercizio")
    args = p.parse_args()
    export(args.category, args.subcategory, args.output, args.db, args.video_id, args.exercise_id)


if __name__ == "__main__":
    main()
