from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable

from db import DEFAULT_DB, ROOT, connect, init_db


ALIASES: dict[str, tuple[str, ...]] = {
    "1 vs 1": ("1 contro 1",),
    "uscita 1 contro 1": ("uscita", "1 contro 1"),
    "reattivita": ("reattività",),
    "reazione": ("reattività",),
    "esplosivita": ("esplosività",),
    "forza esplosiva": ("esplosività",),
    "potenza": ("esplosività",),
    "potenza degli arti inferiori": ("esplosività", "arti inferiori"),
    "caduta laterale": ("tuffo laterale",),
    "cadute laterali": ("tuffo laterale",),
    "tuffi laterali": ("tuffo laterale",),
    "cadute consecutive": ("tuffi consecutivi",),
    "caduta diagonale": ("tuffo diagonale",),
    "caduta bassa": ("tuffo basso",),
    "caduta media": ("tuffo a media altezza",),
    "cadute": ("tuffo laterale",),
    "difesa alta": ("parata alta",),
    "difesa bassa": ("parata bassa",),
    "difesa con il piede": ("parata di piede",),
    "chiusura secondo palo": ("secondo palo",),
    "copertura primo palo": ("primo palo",),
    "contromovimento laterale": ("cambio di direzione laterale",),
    "controllo del tronco": ("stabilità del tronco",),
    "ricezione palla": ("ricezione",),
    "palla al viso": ("presa alta",),
    "palla radente": ("presa bassa",),
    "pallone a terra": ("presa bassa",),
    "pallone rasoterra": ("tiro rasoterra",),
    "rasoterra": ("tiro rasoterra",),
    "palla rimbalzante": ("presa su rimbalzo",),
    "palla rimbalzante verticale": ("presa su rimbalzo",),
    "palloni alti": ("presa alta",),
    "presa rasoterra": ("presa bassa",),
    "tiri ravvicinati": ("tiro ravvicinato",),
    "parate ravvicinate": ("tiro ravvicinato",),
    "conclusione ravvicinata": ("tiro ravvicinato",),
    "situazionale a croce": ("parata a croce",),
    "uscita a croce": ("uscita", "parata a croce"),
    "scivolata": ("parata in spaccata",),
    "spaccata": ("parata in spaccata",),
    "gamba singola": ("salto monopodalico",),
    "una gamba": ("salto monopodalico",),
    "due gambe": ("salto bipodalico",),
    "piedi uniti": ("salto bipodalico",),
    "salti in avanti": ("salto in avanti",),
    "affondi": ("affondo",),
    "split squat bulgaro": ("squat bulgaro",),
    "box jump": ("salto sul box",),
    "leg raise": ("sollevamento gambe",),
    "knee tuck": ("richiamo ginocchia",),
    "alternanza destra sinistra": ("lati alternati",),
    "allenamento a corpo libero": ("corpo libero",),
    "stabilità": ("stabilità del tronco",),
    "seconda presa": ("doppia presa",),
    "anche": ("estensione dell'anca",),
    "avambracci": ("appoggio sugli avambracci",),
}

IGNORED_TAGS = {
    "addominali",
    "allenamento portiere",
    "alternato",
    "box",
    "calcio",
    "core",
    "esercizi all'aperto",
    "estensione",
    "fitness",
    "futsal",
    "gambe",
    "pali",
    "pallone",
    "parata",
    "parate",
    "porta",
    "portiere",
    "presa",
    "salti",
    "salto",
    "spostamenti",
    "tappetino",
    "tattica portiere",
    "tecnica",
    "tuffo",
}


def normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value)).strip().lower()
    return re.sub(r"\s+", " ", text)


def normalize_tags(
    tags: Iterable[object],
    *,
    category: str = "",
    subcategory: str = "",
) -> list[str]:
    redundant = {normalized_text(category)}
    redundant.update(normalized_text(part) for part in subcategory.split("/") if part.strip())
    result: list[str] = []
    for raw_tag in tags:
        tag = normalized_text(raw_tag)
        if not tag:
            continue
        for canonical in ALIASES.get(tag, (tag,)):
            if canonical in IGNORED_TAGS or canonical in redundant or canonical in result:
                continue
            result.append(canonical)
    return result


def normalize_payload(payload: dict) -> dict:
    payload["video_tags"] = normalize_tags(payload.get("video_tags", []))
    for exercise in payload.get("exercises", []):
        exercise["tags"] = normalize_tags(
            exercise.get("tags", []),
            category=str(exercise.get("category", "")),
            subcategory=str(exercise.get("subcategory", "")),
        )
    return payload


def normalize_json_files(root: Path) -> int:
    count = 0
    for path in root.rglob("ai_result*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(
            json.dumps(normalize_payload(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        count += 1
    return count


def _replace_links(con, table: str, owner_column: str, owner_id: int, tags: list[str]) -> None:
    con.execute(f"DELETE FROM {table} WHERE {owner_column}=?", (owner_id,))
    for tag in tags:
        con.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
        tag_id = con.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()["id"]
        con.execute(
            f"INSERT OR IGNORE INTO {table}({owner_column}, tag_id) VALUES (?, ?)",
            (owner_id, int(tag_id)),
        )


def normalize_database(db_path: Path) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        exercises = con.execute("SELECT id, category, subcategory FROM exercises").fetchall()
        for exercise in exercises:
            tags = [
                row["name"] for row in con.execute(
                    "SELECT t.name FROM tags t JOIN exercise_tags et ON et.tag_id=t.id WHERE et.exercise_id=?",
                    (exercise["id"],),
                )
            ]
            _replace_links(
                con,
                "exercise_tags",
                "exercise_id",
                int(exercise["id"]),
                normalize_tags(tags, category=exercise["category"], subcategory=exercise["subcategory"]),
            )
        videos = con.execute("SELECT DISTINCT video_id FROM video_tags").fetchall()
        for video in videos:
            tags = [
                row["name"] for row in con.execute(
                    "SELECT t.name FROM tags t JOIN video_tags vt ON vt.tag_id=t.id WHERE vt.video_id=?",
                    (video["video_id"],),
                )
            ]
            _replace_links(
                con,
                "video_tags",
                "video_id",
                int(video["video_id"]),
                normalize_tags(tags),
            )
        con.execute(
            "DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM exercise_tags UNION SELECT tag_id FROM video_tags)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalizza i tag della pytrainer-library")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json-root", type=Path, default=ROOT / "analysis")
    parser.add_argument("--apply", action="store_true", help="Aggiorna JSON e database esistenti")
    args = parser.parse_args()
    if not args.apply:
        parser.error("specifica --apply per modificare i dati")
    count = normalize_json_files(args.json_root)
    normalize_database(args.db)
    print(f"Normalizzati {count} JSON e il database {args.db}")


if __name__ == "__main__":
    main()
