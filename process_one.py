import json
import os
import sys

from csv_utils import parse_esercizi_csv
from video_helper import search_youtube, extract_start_finish_frames, VideoSearchError, FrameExtractionError

idx = int(sys.argv[1])
os.makedirs("state", exist_ok=True)
out_path = f"state/{idx}.json"

if os.path.exists(out_path):
    print("gia' processato, salto:", out_path)
    sys.exit(0)

esercizi = parse_esercizi_csv("scheda.csv")
e = esercizi[idx]
print(f"=== [{idx}] {e['nome']} ===")

esito = {"nome": e["nome"], "frame_start": None, "frame_finish": None, "errore": None}

try:
    risultati = search_youtube(e["nome"], max_results=3)
except VideoSearchError as exc:
    esito["errore"] = f"ricerca fallita: {exc}"
    risultati = []

for video in risultati:
    durata = video.get("duration") or 60
    print("  provo:", video["title"], durata)
    try:
        fs, ff = extract_start_finish_frames(
            video["webpage_url"], durata * 0.10, durata * 0.50, e["nome"])
        esito["frame_start"] = fs
        esito["frame_finish"] = ff
        esito["errore"] = None
        esito["video_url"] = video["webpage_url"]
        print("  OK:", fs, ff)
        break
    except (VideoSearchError, FrameExtractionError) as exc:
        print("  fallito:", exc)
        esito["errore"] = str(exc)
        continue

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(esito, f, ensure_ascii=False, indent=2)

print("salvato:", out_path)
