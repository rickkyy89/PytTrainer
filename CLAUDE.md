# Istruzioni per Claude Cowork — Workout Sheet Automator

App per generare schede d'allenamento A4 su Google Docs: esercizi da CSV, video
dimostrativi da YouTube (yt-dlp), frame START/FINISH estratti con ffmpeg.
Per l'uso **automatico** NON usare l'interfaccia Streamlit: chiama direttamente
i moduli Python del progetto.

## Moduli riusabili

| Funzione | Modulo | Scopo |
|---|---|---|
| `parse_esercizi_csv(file)` → `list[dict]` | `csv_utils.py` | Legge/valida il CSV (solleva `ValueError` se malformato) |
| `search_youtube(nome, max_results=3)` → `list[dict]` | `video_helper.py` | Risultati con `id`, `title`, `duration`, `webpage_url` |
| `extract_start_finish_frames(url, ts_start, ts_finish, nome)` → `(path_start, path_finish)` | `video_helper.py` | Estrae i 2 frame in `frames/` senza scaricare il video |
| `create_workout_document(esercizi, titolo)` → `{"document_id", "url"}` | `google_docs_helper.py` | Genera il Google Doc A4 e ne restituisce l'URL |

## 1. Installazione (una sola volta)

```bash
pip install -r requirements.txt
ffmpeg -version || sudo apt install -y ffmpeg   # macOS: brew install ffmpeg
```

Verifica le credenziali Google: deve esistere `credentials.json` (OAuth) o
`service_account.json` nella root. **Se mancano, fermati e chiedile all'utente**
(vedi README per crearle): questo passo non è automatizzabile. Il primo login
OAuth apre il browser dell'utente e crea `token.json`, poi tutto è automatico.

## 2. Creazione del CSV

Colonne obbligatorie: `Nome,Spiegazione,Note,Ripetizioni,Recupero`
(esempio completo in `esercizi_example.csv`). Se l'utente fornisce solo i nomi
degli esercizi, compila tu spiegazione (2-3 frasi tecniche), note (1-2 frasi),
ripetizioni (es. `3x12`) e recupero (es. `90 SEC`). Salva come `scheda.csv` e
valida subito con `parse_esercizi_csv("scheda.csv")`.

## 3. Flusso automatico completo (CSV → Google Doc)

```python
from csv_utils import parse_esercizi_csv
from video_helper import search_youtube, extract_start_finish_frames, VideoSearchError, FrameExtractionError
from google_docs_helper import create_workout_document

esercizi = parse_esercizi_csv("scheda.csv")

for e in esercizi:
    for video in search_youtube(e["nome"]):          # prova i risultati in ordine
        durata = video.get("duration") or 60
        try:
            # Default ragionevoli: posizione iniziale ~10%, finale ~50% del video
            e["frame_start"], e["frame_finish"] = extract_start_finish_frames(
                video["webpage_url"], durata * 0.10, durata * 0.50, e["nome"])
            break
        except (VideoSearchError, FrameExtractionError):
            continue                                  # video successivo

pronti = [e for e in esercizi if e.get("frame_start") and e.get("frame_finish")]
risultato = create_workout_document(pronti, "SCHEDA 1: GAMBE & GLUTEI")
print(risultato["url"])                               # riporta questo URL all'utente
```

Al termine comunica all'utente l'URL del documento e quali esercizi (se ce ne
sono) sono rimasti senza video utilizzabile.

## 4. Uso manuale alternativo

`streamlit run app.py` — l'utente sceglie video e timestamp dall'interfaccia.

## Errori noti

- `VideoSearchError`: video non raggiungibile → passa al risultato successivo.
- `FrameExtractionError`: stream/timestamp non validi → cambia timestamp o video.
- `GoogleAuthError`: credenziali mancanti/invalide → chiedi all'utente, non tentare workaround.
- Token scaduto: elimina `token.json` e rifai il login OAuth.
