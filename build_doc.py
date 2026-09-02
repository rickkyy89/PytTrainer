import json

from core.csv_utils import parse_esercizi_csv
from core.docs_helper import create_workout_document

esercizi = parse_esercizi_csv("scheda.csv")

pronti = []
mancanti = []
for i, e in enumerate(esercizi):
    with open(f"state/{i}.json", encoding="utf-8") as f:
        stato = json.load(f)
    if stato.get("frame_start") and stato.get("frame_finish"):
        e["frame_start"] = stato["frame_start"]
        e["frame_finish"] = stato["frame_finish"]
        pronti.append(e)
    else:
        mancanti.append(e["nome"])

print(f"{len(pronti)}/{len(esercizi)} esercizi pronti.")
if mancanti:
    print("Mancanti:", mancanti)

risultato = create_workout_document(pronti, "SCHEDA 1: CORREZIONE POSTURALE E STABILITA")
print("DOCUMENTO URL:", risultato["url"])
