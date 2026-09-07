from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analysis_io import validate_result, validate_video_tags
from db import connect, init_db, replace_exercises_for_video, replace_video_tags, upsert_video
from analyze import sample_timestamps
from export_pytrainer import export
from tag_policy import normalize_tags
from video_prepare import VideoPrepareError, prepare_video, slugify


def test_database_smoke(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    with connect(db) as con:
        video_id, created = upsert_video(
            con,
            canonical_url="https://www.youtube.com/watch?v=abc",
            original_url="https://youtu.be/abc",
            platform="youtube",
            external_id="abc",
            title="Test",
        )
        assert created
        _, created2 = upsert_video(
            con,
            canonical_url="https://www.youtube.com/watch?v=abc",
            original_url="https://www.youtube.com/watch?v=abc",
            platform="youtube",
            external_id="abc",
        )
        assert not created2
        replace_exercises_for_video(con, video_id, [{
            "name": "Esercizio test",
            "category": "Portiere",
            "subcategory": "Situazionale / Uscita",
            "description": "Test",
            "timestamp_start": 1.0,
            "timestamp_finish": 2.0,
            "confidence": "HIGH",
            "tags": ["test"],
        }])
        assert con.execute("SELECT COUNT(*) FROM exercises").fetchone()[0] == 1
        assert con.execute("SELECT status FROM videos WHERE id=?", (video_id,)).fetchone()[0] == "ANALYZED"


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def download(self, _urls):
        path = Path(self.options["outtmpl"].replace("%(ext)s", "mp4"))
        path.write_bytes(b"fake video")


def add_test_video(db: Path, title: str = "Test Video") -> int:
    init_db(db)
    with connect(db) as con:
        video_id, _ = upsert_video(
            con,
            canonical_url="https://www.youtube.com/watch?v=test",
            original_url="https://youtu.be/test",
            platform="youtube",
            external_id="test",
            title=title,
        )
    return video_id


def test_prepare_video_downloads_with_limited_format_and_marks_ready(tmp_path):
    db = tmp_path / "test.db"
    video_id = add_test_video(db, "Tést Video!")
    output_dir = tmp_path / "videos" / "youtube"

    path = prepare_video(video_id, db, output_dir, ydl_factory=FakeYoutubeDL)

    assert path.name == "0001_test-video.mp4"
    assert path.read_bytes() == b"fake video"
    with connect(db) as con:
        row = con.execute("SELECT status, local_path FROM videos WHERE id=?", (video_id,)).fetchone()
    assert row["status"] == "READY_FOR_ANALYSIS"
    assert row["local_path"] == str(path)


def test_prepare_video_reuses_valid_local_file_without_downloading(tmp_path):
    db = tmp_path / "test.db"
    video_id = add_test_video(db)
    existing = tmp_path / "existing.mp4"
    existing.write_bytes(b"existing video")
    with connect(db) as con:
        con.execute("UPDATE videos SET local_path=? WHERE id=?", (str(existing), video_id))

    path = prepare_video(video_id, db, tmp_path / "unused", ydl_factory=lambda _: (_ for _ in ()).throw(AssertionError()))

    assert path == existing
    with connect(db) as con:
        assert con.execute("SELECT status FROM videos WHERE id=?", (video_id,)).fetchone()[0] == "READY_FOR_ANALYSIS"


def test_discard_local_video_keeps_analyzed_record(tmp_path):
    from video_prepare import discard_local_video

    db = tmp_path / "test.db"
    video_id = add_test_video(db)
    existing = tmp_path / "existing.mp4"
    existing.write_bytes(b"existing video")
    with connect(db) as con:
        con.execute("UPDATE videos SET status='ANALYZED', local_path=? WHERE id=?", (str(existing), video_id))

    assert discard_local_video(video_id, db) == existing
    assert not existing.exists()
    with connect(db) as con:
        row = con.execute("SELECT status, local_path FROM videos WHERE id=?", (video_id,)).fetchone()
    assert row["status"] == "ANALYZED"
    assert row["local_path"] == ""


def test_prepare_video_marks_error_when_download_fails(tmp_path):
    db = tmp_path / "test.db"
    video_id = add_test_video(db, "")

    class FailingYoutubeDL(FakeYoutubeDL):
        def download(self, _urls):
            raise RuntimeError("unavailable")

    try:
        prepare_video(video_id, db, tmp_path / "videos", ydl_factory=FailingYoutubeDL)
    except VideoPrepareError:
        pass
    else:
        raise AssertionError("Expected VideoPrepareError")
    with connect(db) as con:
        assert con.execute("SELECT status FROM videos WHERE id=?", (video_id,)).fetchone()[0] == "ERROR"


def test_slugify_has_stable_ascii_fallback():
    assert slugify("Tést Video!") == "test-video"
    assert slugify("") == "untitled"


def test_validate_result_checks_timestamps_and_numeric_confidence(tmp_path):
    db = tmp_path / "test.db"
    video_id = add_test_video(db)
    with connect(db) as con:
        con.execute("UPDATE videos SET duration=60 WHERE id=?", (video_id,))
    result = validate_result({"video_id": video_id, "exercises": [{
        "name": "Uscita 1 contro 1",
        "timestamp_start": 12,
        "timestamp_finish": 30,
        "confidence": 0.8,
        "tags": ["uscita"],
    }]}, db)
    assert result[0]["confidence"] == 0.8


def test_validate_result_rejects_invalid_timestamp_range(tmp_path):
    db = tmp_path / "test.db"
    video_id = add_test_video(db)
    try:
        validate_result({"video_id": video_id, "exercises": [{
            "name": "Test", "timestamp_start": 20, "timestamp_finish": 20, "confidence": 0.5,
        }]}, db)
    except ValueError as exc:
        assert "finish" in str(exc)
    else:
        raise AssertionError("Expected invalid timestamp validation")


def test_sample_timestamps_are_distributed_inside_video():
    assert sample_timestamps(130, 3) == [32.5, 65.0, 97.5]


def test_export_can_select_a_single_video(tmp_path):
    db = tmp_path / "test.db"
    first_id = add_test_video(db)
    with connect(db) as con:
        second_id, _ = upsert_video(
            con,
            canonical_url="https://www.youtube.com/watch?v=second",
            original_url="https://youtu.be/second",
            platform="youtube",
        )
        replace_exercises_for_video(con, first_id, [{"name": "Primo"}])
        replace_exercises_for_video(con, second_id, [{"name": "Secondo"}])

    output = tmp_path / "video.csv"
    export(None, None, output, db, [first_id])

    content = output.read_text(encoding="utf-8-sig")
    assert "Primo" in content
    assert "Secondo" not in content


def test_export_can_select_exercise_ids(tmp_path):
    db = tmp_path / "test.db"
    video_id = add_test_video(db)
    with connect(db) as con:
        replace_exercises_for_video(con, video_id, [{"name": "Primo"}, {"name": "Secondo"}])
        exercise_id = con.execute("SELECT id FROM exercises WHERE name='Secondo'").fetchone()[0]

    output = tmp_path / "exercise.csv"
    export(None, None, output, db, exercise_ids=[exercise_id])

    content = output.read_text(encoding="utf-8-sig")
    assert "Primo" not in content
    assert "Secondo" in content


def test_video_tags_are_stored_separately_from_exercise_tags(tmp_path):
    db = tmp_path / "test.db"
    video_id = add_test_video(db)
    with connect(db) as con:
        replace_video_tags(con, video_id, ["riscaldamento"])
        tags = con.execute(
            "SELECT t.name FROM tags t JOIN video_tags vt ON vt.tag_id=t.id WHERE vt.video_id=?",
            (video_id,),
        ).fetchall()
    assert [row["name"] for row in tags] == ["riscaldamento"]
    assert validate_video_tags({"video_tags": ["riscaldamento"]}) == ["riscaldamento"]


def test_tag_policy_normalizes_aliases_and_removes_generic_tags():
    assert normalize_tags(
        ["1 vs 1", "Portiere", "uscita a croce", "situazionale a croce", "Reattivita"],
        category="Situazionale",
        subcategory="1 contro 1",
    ) == ["uscita", "parata a croce", "reattività"]
