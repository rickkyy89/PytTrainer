# Istruzioni per Claude Cowork — Workout Sheet Automator

App per generare schede d'allenamento A4 su Google Docs: esercizi da manifest
CSV, video dimostrativi da YouTube (yt-dlp), frame START/FINISH estratti con
ffmpeg. Ogni allenamento vive in **un unico file `.scheda`** (uno zip: CSV +
frames + stato di ripresa) — niente cartella `frames/` condivisa né CSV
sciolti. Per l'uso **automatico** NON usare l'interfaccia Streamlit: chiama
direttamente i moduli Python del progetto.

## Il file `.scheda`

`mia_scheda.scheda` è uno zip con dentro: `scheda.csv` (manifest, stesse
colonne di sempre, percorsi frame relativi tipo `frames/<slug>_start.jpg`),
`frames/*.jpg` e `state.json` (opzionale, ripresa Google Doc). Al caricamento
viene estratto nella cartella di lavoro `<percorso>.work/` (cache usa-e-getta,
cancellarla è sempre sicuro: la fonte di verità è il bundle). Il salvataggio
ricompatta tutto in modo atomico.

## Moduli riusabili

| Funzione | Modulo | Scopo |
|---|---|---|
| `carica_scheda(percorso)` → `(list[dict], cartella_lavoro)` | `core.scheda_file` | Apre un `.scheda`, estrae frames/stato in `<percorso>.work/` e ritorna gli esercizi con i percorsi frame già puntati ai file estratti (solleva `SchedaFileError` / `ValueError`) |
| `salva_scheda(esercizi, percorso, state_path=None)` | `core.scheda_file` | Riscrive il `.scheda` (manifest + frames esistenti + stato se presente), scrittura atomica |
| `cartella_frames(cartella_lavoro)` → `str` | `core.scheda_file` | Cartella dei frame del bundle: è l'`output_dir` da passare a `scegli_ed_estrai` / `extract_start_finish_frames` |
| `percorso_stato(cartella_lavoro)` → `str` | `core.scheda_file` | Percorso dello `state.json` del bundle: è lo `state_path` da passare a `create_workout_document` / `update_exercise_media` |
| `scheda_bytes(esercizi, state_path=None)` → `bytes` | `core.scheda_file` | Stesso archivio di `salva_scheda` ma in memoria (download da UI) |
| `parse_esercizi_csv(file)` → `list[dict]` | `core.csv_utils` | Legge/valida un CSV manifest nudo (solleva `ValueError` se malformato) — utile per creare una scheda da un CSV |
| `search_youtube(nome, max_results=3)` → `list[dict]` | `core.video_helper` | Risultati con `id`, `title`, `duration`, `webpage_url` |
| `extract_start_finish_frames(url, ts_start, ts_finish, nome, output_dir)` → `(path_start, path_finish)` | `core.video_helper` | Estrae i 2 frame in `output_dir` senza scaricare il video |
| `get_video_info(url)` → `{"duration", "title"}` | `core.video_helper` | Info di un video puntuale (senza download), per l'euristica timestamp |
| `scegli_ed_estrai(esercizio, output_dir="frames", logger=print)` → `dict` | `core.video_helper` | Orchestrazione: rispetta VideoURL/timestamp/frame già nel manifest, altrimenti cerca+filtra+estrae |
| `create_workout_document(esercizi, titolo, state_path=None, ...)` → `{"document_id", "url", "esercizi_inseriti"}` | `core.docs_helper` | Genera (o riprende) il Google Doc A4 raggruppato per sezioni |
| `update_exercise_media(doc_id, nome_esercizio, video_url, ..., output_dir=...)` → `dict` | `core.docs_helper` | Sostituisce mirata mente i frame di UN esercizio già nel documento |
| `get_credentials_manual_flow(auth_code=None)` | `core.docs_helper` | OAuth headless: prima chiamata dà l'URL, seconda con `auth_code` completa il login |
| `crop_frame(path, sinistra_pct, alto_pct, destra_pct, basso_pct)` | `core.video_helper` | Ritaglia un frame estratto (percentuali per lato, sovrascrive il file) |
| `importa_frame_da_immagine(path_immagine, nome_esercizio, suffisso, output_dir)` → `str` | `core.video_helper` | Usa un'immagine dell'utente al posto del frame estratto: la converte in JPEG col nome canonico `<slug>_start.jpg`/`<slug>_finish.jpg` (`suffisso` = `"start"`/`"finish"`), sostituendo il frame esistente |
| `LocalCredentialsProvider(base_dir)` / `PcFfmpegBackend()` | `core.platform` | Implementazioni PC iniettabili per credenziali Google e ffmpeg; il core non cerca più credenziali rispetto alla CWD |

## 1. Installazione (una sola volta)

```bash
pip install -r requirements.txt
ffmpeg -version || sudo apt install -y ffmpeg   # macOS: brew install ffmpeg
```

Verifica le credenziali Google: deve esistere `credentials.json` (OAuth) o
`service_account.json` nella root. **Se mancano, fermati e chiedile all'utente**
(vedi README per crearle): questo passo non è automatizzabile. Il primo login
OAuth apre il browser dell'utente e crea `token.json`, poi tutto è automatico.

## 2. Creazione di una nuova scheda

Colonne obbligatorie del manifest: `Nome,Spiegazione,Note,Ripetizioni,Recupero`
(esempio completo in `esercizi_example.csv`). Se l'utente fornisce solo i nomi
degli esercizi, compila tu spiegazione (2-3 frasi tecniche), note (1-2 frasi),
ripetizioni (es. `3x12`) e recupero (es. `90 SEC`). Un CSV nudo serve solo
come input di partenza: costruisci gli esercizi (da CSV con
`parse_esercizi_csv`, o direttamente come lista di dict) e salvali subito nel
file unico con `salva_scheda(esercizi, "mia_scheda.scheda")` — da lì in poi
l'artefatto persistente è il `.scheda`, non il CSV.

## 3. Flusso automatico completo (.scheda → Google Doc)

Il `.scheda` è il manifest persistente dell'allenamento: `scegli_ed_estrai`
rispetta le scelte già presenti (VideoURL/timestamp/frame) e `salva_scheda`
le ricompatta nel bundle, così rilanciare lo stesso script è idempotente.

```python
from core.scheda_file import carica_scheda, salva_scheda, cartella_frames, percorso_stato
from core.video_helper import scegli_ed_estrai
from core.docs_helper import create_workout_document
from core.platform import LocalCredentialsProvider, PcFfmpegBackend
from pathlib import Path

base_dir = Path(__file__).resolve().parent
credential_provider = LocalCredentialsProvider(base_dir)
ffmpeg_backend = PcFfmpegBackend()

esercizi, lavoro = carica_scheda("mia_scheda.scheda", base_dir=base_dir)
for e in esercizi:
    scegli_ed_estrai(e, output_dir=cartella_frames(lavoro), ffmpeg_backend=ffmpeg_backend)
salva_scheda(esercizi, "mia_scheda.scheda", base_dir=base_dir)  # checkpoint: frame nel bundle

pronti = [e for e in esercizi if e.get("frame_start") and e.get("frame_finish")]
stato = percorso_stato(lavoro)
risultato = create_workout_document(
    pronti, "SCHEDA 1: GAMBE & GLUTEI", state_path=stato,
    credential_provider=credential_provider, base_dir=base_dir)
salva_scheda(esercizi, "mia_scheda.scheda", state_path=stato, base_dir=base_dir)  # stato dentro il bundle
print(risultato["url"])                                # riporta questo URL all'utente
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
| `FrameStartPath` / `FrameFinishPath` | Frame già estratti (nel bundle: `frames/<slug>_start.jpg`) | Ri-estrazione |

Se per un esercizio l'utente fornisce immagini proprie invece di un video,
passale a `importa_frame_da_immagine(...)` con `output_dir=cartella_frames(lavoro)`
e scrivi il percorso restituito in `frame_start` / `frame_finish`: da lì in poi
l'esercizio è identico a uno con frame estratti (`scegli_ed_estrai` li rispetta
e non ri-estrae, `salva_scheda` li mette nel bundle).

### Ripresa dopo interruzione

`create_workout_document(..., state_path=...)` salva un checkpoint dopo OGNI
esercizio inserito; `salva_scheda(..., state_path=stato)` lo porta dentro il
bundle. Se l'esecuzione si interrompe, rilanciare lo STESSO flusso sullo
stesso `.scheda`: `carica_scheda` ri-estrae frame e `state.json`,
`scegli_ed_estrai` salta i frame già presenti e `create_workout_document`
riusa il documento aggiungendo solo gli esercizi mancanti. Per ripartire da
zero: cancellare lo `state.json` nella cartella di lavoro e risalvare il
bundle senza `state_path`.

Se il Google Doc a cui punta lo stato è stato cancellato da Drive (404),
`create_workout_document` non fallisce: scarta lo stato orfano e rigenera la
scheda in un documento nuovo con tutti gli esercizi, segnalandolo con
`risultato["documento_rigenerato"] is True` (da riportare all'utente insieme
al nuovo URL, che è cambiato).

### Correzione mirata di un video/timestamp

Correggi `video_url` e/o `ts_start`/`ts_finish` dell'esercizio (negli
esercizi caricati o a mano nel manifest), poi:

```python
from core.scheda_file import carica_scheda, salva_scheda, cartella_frames, percorso_stato
from core.docs_helper import update_exercise_media
from core.platform import LocalCredentialsProvider, PcFfmpegBackend
from pathlib import Path

base_dir = Path(__file__).resolve().parent
credential_provider = LocalCredentialsProvider(base_dir)
ffmpeg_backend = PcFfmpegBackend()

esercizi, lavoro = carica_scheda("mia_scheda.scheda", base_dir=base_dir)
update_exercise_media(
    doc_id, "Nome esercizio", video_url="https://...",
    ts_start=12.0, ts_finish=48.0,
    state_path=percorso_stato(lavoro),
    output_dir=cartella_frames(lavoro),
    credential_provider=credential_provider, base_dir=base_dir,
    ffmpeg_backend=ffmpeg_backend)
salva_scheda(esercizi, "mia_scheda.scheda", state_path=percorso_stato(lavoro), base_dir=base_dir)
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
