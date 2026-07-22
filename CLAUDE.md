# Istruzioni per Claude Cowork — Workout Sheet Automator

App per generare schede d'allenamento A4 su Google Docs: esercizi da CSV, video
dimostrativi da YouTube (yt-dlp), frame START/FINISH estratti con ffmpeg.
Per l'uso **automatico** NON usare l'interfaccia Streamlit: chiama direttamente
i moduli Python del progetto.

## Moduli riusabili

| Funzione | Modulo | Scopo |
|---|---|---|
| `parse_esercizi_csv(file)` → `list[dict]` | `csv_utils.py` | Legge/valida il CSV manifest (solleva `ValueError` se malformato) |
| `scrivi_esercizi_csv(esercizi, percorso)` | `csv_utils.py` | Riscrive il CSV arricchito con le scelte fatte (round-trip col parse) |
| `search_youtube(nome, max_results=3)` → `list[dict]` | `video_helper.py` | Risultati con `id`, `title`, `duration`, `webpage_url` |
| `extract_start_finish_frames(url, ts_start, ts_finish, nome)` → `(path_start, path_finish)` | `video_helper.py` | Estrae i 2 frame in `frames/` senza scaricare il video |
| `get_video_info(url)` → `{"duration", "title"}` | `video_helper.py` | Info di un video puntuale (senza download), per l'euristica timestamp |
| `scegli_ed_estrai(esercizio, output_dir="frames", logger=print)` → `dict` | `video_helper.py` | Orchestrazione: rispetta VideoURL/timestamp/frame già nel manifest, altrimenti cerca+filtra+estrae |
| `create_workout_document(esercizi, titolo, state_path=None, ...)` → `{"document_id", "url", "esercizi_inseriti"}` | `google_docs_helper.py` | Genera (o riprende) il Google Doc A4 raggruppato per sezioni |
| `percorso_stato_per_titolo(titolo)` → `str` | `google_docs_helper.py` | Percorso convenzionale del file `*.state.json` di una scheda |
| `update_exercise_media(doc_id, nome_esercizio, video_url, ...)` → `dict` | `google_docs_helper.py` | Sostituisce mirata mente i frame di UN esercizio già nel documento |
| `get_credentials_manual_flow(auth_code=None)` | `google_docs_helper.py` | OAuth headless: prima chiamata dà l'URL, seconda con `auth_code` completa il login |

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

Il CSV è il manifest persistente della scheda: `scegli_ed_estrai` rispetta le
scelte già presenti (VideoURL/timestamp/frame) e `scrivi_esercizi_csv` le
salva di nuovo, così rilanciare lo stesso script è idempotente.

```python
from csv_utils import parse_esercizi_csv, scrivi_esercizi_csv
from video_helper import scegli_ed_estrai
from google_docs_helper import create_workout_document, percorso_stato_per_titolo

esercizi = parse_esercizi_csv("scheda.csv")
for e in esercizi:
    scegli_ed_estrai(e)                     # rispetta VideoURL/timestamp/frame già nel CSV
scrivi_esercizi_csv(esercizi, "scheda.csv") # arricchisce il CSV = salvataggio della scheda

pronti = [e for e in esercizi if e.get("frame_start") and e.get("frame_finish")]
risultato = create_workout_document(
    pronti, "SCHEDA 1: GAMBE & GLUTEI",
    state_path=percorso_stato_per_titolo("SCHEDA 1: GAMBE & GLUTEI"))
print(risultato["url"])                               # riporta questo URL all'utente
```

Al termine comunica all'utente l'URL del documento, il log delle scelte video
stampato da `scegli_ed_estrai` (video scelto e video scartati con motivo, per
ogni esercizio) e quali esercizi (se ce ne sono) sono rimasti senza video
utilizzabile.

### Colonne opzionali del manifest CSV

| Colonna | Significato | Se assente/vuota |
|---|---|---|
| `Gruppo` | Sezione della scheda (es. `Attivazione`) | Gruppo implicito, nessuna intestazione |
| `VideoURL` | Video YouTube forzato | Ricerca automatica + filtro di pertinenza |
| `TimestampStart` / `TimestampFinish` | Secondi dei frame START/FINISH | Euristica 10%/50% della durata |
| `FrameStartPath` / `FrameFinishPath` | Percorso dei frame già estratti | Ri-estrazione |

### Ripresa dopo interruzione

`create_workout_document(..., state_path=...)` salva un checkpoint
(`<slug_titolo>.state.json`) dopo OGNI esercizio inserito. Se l'esecuzione si
interrompe, rilanciare lo STESSO flusso (stesso `scheda.csv` e stesso
`state_path`): il documento esistente viene riusato e solo gli esercizi
mancanti vengono aggiunti. Per ripartire da zero, cancellare il file di stato.

### Correzione mirata di un video/timestamp

Modifica a mano `VideoURL` e/o `TimestampStart`/`TimestampFinish` nel CSV per
l'esercizio da correggere, poi:

```python
from google_docs_helper import update_exercise_media, percorso_stato_per_titolo

update_exercise_media(
    doc_id, "Nome esercizio", video_url="https://...",
    ts_start=12.0, ts_finish=48.0,
    state_path=percorso_stato_per_titolo("SCHEDA 1: GAMBE & GLUTEI"))
```

Sostituisce solo le due immagini di quell'esercizio nel documento già
generato, senza rigenerare tutto.

### Autenticazione in ambienti senza browser (headless)

Se `get_credentials()` non può aprire un browser locale, usa
`get_credentials_manual_flow()`:

1. Prima chiamata senza `auth_code`: solleva `GoogleAuthError` con dentro
   l'URL di autorizzazione — dallo all'utente e chiedigli di aprirlo,
   autorizzare e incollarti il `code` (o l'intero URL di redirect, anche se
   la pagina non si carica).
2. Seconda chiamata con `auth_code=<code o URL incollato>`: completa il
   login e salva `token.json`.

## 4. Uso manuale alternativo

`streamlit run app.py` — l'utente sceglie video e timestamp dall'interfaccia.

## Errori noti

- `VideoSearchError`: video non raggiungibile → passa al risultato successivo.
- `FrameExtractionError`: stream/timestamp non validi → cambia timestamp o video.
- `GoogleAuthError`: credenziali mancanti/invalide → chiedi all'utente (o usa
  `get_credentials_manual_flow()` in ambienti headless), non tentare workaround.
- Token scaduto: elimina `token.json` e rifai il login OAuth.
