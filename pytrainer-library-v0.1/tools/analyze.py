from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from db import DEFAULT_DB, ROOT, connect
from video_prepare import is_valid_file


WORK_ROOT = ROOT / "analysis" / "work"


class AnalysisPreparationError(RuntimeError):
    """The local video cannot be prepared for visual analysis."""


def local_video_path(local_path: str) -> Path:
    path = Path(local_path)
    return path if path.is_absolute() else ROOT / path


def sample_timestamps(duration: float, count: int = 12) -> list[float]:
    if duration <= 0:
        raise AnalysisPreparationError("Durata video non valida")
    return [round(duration * index / (count + 1), 2) for index in range(1, count + 1)]


def run_ffmpeg(arguments: list[str]) -> None:
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments], check=True)
    except FileNotFoundError as exc:
        raise AnalysisPreparationError("ffmpeg non trovato nel PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise AnalysisPreparationError("ffmpeg non ha potuto estrarre i frame") from exc


def prepare_analysis_input(video_id: int, db_path: Path = DEFAULT_DB, frame_count: int = 12) -> Path:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    if row is None:
        raise AnalysisPreparationError(f"Video #{video_id} non trovato")

    video = dict(row)
    source = local_video_path(video["local_path"])
    if not is_valid_file(source):
        raise AnalysisPreparationError(f"Video #{video_id} non ha un file locale valido")

    duration = float(video["duration"] or 0)
    work_dir = WORK_ROOT / str(video_id)
    frames_dir = work_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    timestamps = sample_timestamps(duration, frame_count)
    frame_paths: list[Path] = []
    for index, timestamp in enumerate(timestamps, start=1):
        path = frames_dir / f"frame_{index:02d}.jpg"
        run_ffmpeg(["-ss", str(timestamp), "-i", str(source), "-frames:v", "1", "-q:v", "3", str(path)])
        frame_paths.append(path)

    contact_sheet = work_dir / "contact_sheet.jpg"
    run_ffmpeg([
        "-framerate", "1",
        "-start_number", "1",
        "-i", str(frames_dir / "frame_%02d.jpg"),
        "-vf", "scale=320:-2,tile=4x3:padding=8:margin=8",
        "-frames:v", "1",
        str(contact_sheet),
    ])

    metadata = {
        "video_id": video_id,
        "title": video["title"],
        "author": video["author"],
        "url": video["canonical_url"],
        "duration": duration,
        "local_path": video["local_path"],
    }
    (work_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    ai_input = {
        **metadata,
        "contact_sheet": "contact_sheet.jpg",
        "frames": [
            {"timestamp": timestamp, "path": path.relative_to(work_dir).as_posix()}
            for timestamp, path in zip(timestamps, frame_paths)
        ],
        "instruction": (
            "Analizza i frame in sequenza. Identifica zero, uno o piu esercizi; "
            "usa solo dettagli supportati dalle immagini. Rispondi con JSON nel formato "
            "{video_id, video_tags, exercises:[{name, description, notes, category, subcategory, tags, "
            "timestamp_start, timestamp_finish, confidence}]}. Testi in italiano; confidence 0..1."
        ),
    }
    path = work_dir / "ai_input.json"
    path.write_text(json.dumps(ai_input, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara frame e input AI per un video locale")
    parser.add_argument("video_id", type=int)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print(prepare_analysis_input(args.video_id, args.db))


if __name__ == "__main__":
    main()
