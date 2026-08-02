import sys
from csv_utils import parse_esercizi_csv
from video_helper import search_youtube, extract_start_finish_frames, VideoSearchError, FrameExtractionError
from google_docs_helper import create_workout_document

esercizi = parse_esercizi_csv("scheda.csv")

for e in esercizi:
    print(f"\n=== {e['nome']} ===", flush=True)
    trovato = False
    try:
        risultati = search_youtube(e["nome"])
    except VideoSearchError as exc:
        print("  ricerca fallita:", exc)
        risultati = []
    for video in risultati:
        durata = video.get("duration") or 60
        print(f"  provo video: {video['title']} ({durata}s)", flush=True)
        try:
            e["frame_start"], e["frame_finish"] = extract_start_finish_frames(
                video["webpage_url"], durata * 0.10, durata * 0.50, e["nome"])
            print("  OK frame estratti:", e["frame_start"], e["frame_finish"])
            trovato = True
            break
        except (VideoSearchError, FrameExtractionError) as exc:
            print("  fallito:", exc)
            continue
    if not trovato:
        print("  NESSUN VIDEO UTILIZZABILE per", e["nome"])

pronti = [e for e in esercizi if e.get("frame_start") and e.get("frame_finish")]
mancanti = [e["nome"] for e in esercizi if not (e.get("frame_start") and e.get("frame_finish"))]

print(f"\n{len(pronti)}/{len(esercizi)} esercizi pronti con frame.")
if mancanti:
    print("Mancanti:", mancanti)

if pronti:
    risultato = create_workout_document(pronti, "SCHEDA 1: CORREZIONE POSTURALE E STABILITA")
    print("\nDOCUMENTO URL:", risultato["url"])
else:
    print("\nNessun esercizio pronto, documento non creato.")
