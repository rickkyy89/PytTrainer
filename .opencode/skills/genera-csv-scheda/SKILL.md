---
name: genera-csv-scheda
description: Crea CSV iniziali per PytTrainer da richiesta diretta, YouTube o Instagram, con VideoURL e timestamp per ritrovo rapido
---

## Cosa fa
Genera un CSV manifest iniziale (11 colonne) pronto per `csv_utils.parse_esercizi_csv` / `scheda_file.salva_scheda`. Supporta tre sorgenti:
- **richiesta diretta** (es. "5 esercizi per rinforzare l'arcata plantare")
- **YouTube** (singolo video o playlist) - estrae esercizi, salva `VideoURL` + `TimestampStart`/`TimestampFinish`
- **Instagram** (post/reel) - estrae esercizi, salva `VideoURL` + timestamp se ricavabile

Per YouTube/Instagram conviene sempre valorizzare `VideoURL`, `TimestampStart` e `TimestampFinish` cosi' l'utente ritrova il punto esatto del video.

## Quando usarla
Usa questa skill quando l'utente chiede di creare una scheda/CSV di partenza, anche con frasi come "creami un allenamento...", "estrai esercizi da questo video", "fai un csv da questa playlist", con link YouTube/Instagram.

## Formato CSV atteso
Colonne obbligatorie: `Nome,Spiegazione,Note,Ripetizioni,Recupero`
Colonne opzionali: `Gruppo,VideoURL,TimestampStart,TimestampFinish,FrameStartPath,FrameFinishPath`
Ordine canonico: `Nome,Spiegazione,Note,Ripetizioni,Recupero,Gruppo,VideoURL,TimestampStart,TimestampFinish,FrameStartPath,FrameFinishPath`
- `Spiegazione`: 2-3 frasi tecniche
- `Note`: 1-2 frasi di attenzione
- `Ripetizioni`: es. `3x12`, `3x12 per gamba`, `1x60s`
- `Recupero`: es. `60 SEC`, `90 SEC`
- `Gruppo`: sezione (es. `Attivazione`, `Rinforzo Muscolare`) oppure vuoto
- `VideoURL`/`TimestampStart`/`TimestampFinish`: valorizza se fonte e' video; lascia vuoto se richiesta diretta
- `FrameStartPath`/`FrameFinishPath`: lascia vuoto nel CSV iniziale (verra' popolato dopo `scegli_ed_estrai`)

Validazione: usa `csv_utils.scrivi_esercizi_csv` o `csv_utils.esercizi_csv_bytes` per garantire round-trip con `parse_esercizi_csv`. Verifica con `python -c "from csv_utils import parse_esercizi_csv; parse_esercizi_csv('output.csv')"`.

## Workflow

### 1. Capisci la sorgente
- Se l'utente fornisce solo testo -> **richiesta diretta**
- Se contiene `youtube.com`, `youtu.be`, `youtube.com/playlist` -> **YouTube**
- Se contiene `instagram.com` -> **Instagram**
- Se playlist + filtro (es. "solo esercizi per glutei") -> estrai tutti, poi filtra per pertinenza

### 2A. Richiesta diretta
1. Genera lista esercizi coerente con obiettivo, livello, attrezzatura disponibile (chiedi se non specificato, altrimenti assumi corpo libero + elastici).
2. Per ogni esercizio compila `Spiegazione`, `Note`, `Ripetizioni`, `Recupero`, `Gruppo`.
3. Lascia `VideoURL`/`Timestamp*` vuoti.

### 2B. YouTube (video singolo o playlist)
1. Risolvi URL con `yt-dlp` senza download:
   ```python
   import yt_dlp
   opts = {"quiet": True, "skip_download": True}
   with yt_dlp.YoutubeDL(opts) as ydl:
       info = ydl.extract_info(url, download=False)
   # se playlist: info["entries"] contiene i video
   # per ogni video usa info["chapters"] o descrizione con timestamp
   ```
   Alternativa riusa `video_helper.get_video_info(url)` per titolo/durata.
2. Per ogni esercizio rilevato:
   - `Nome` = titolo capitolo o esercizio citato nella descrizione/trascrizione
   - `VideoURL` = `https://www.youtube.com/watch?v={id}` (per playlist, URL specifico del video)
   - `TimestampStart`/`TimestampFinish` = secondi del segmento (da `chapters` se presenti, altrimenti stima 10%/50% o usa timing citato nel video; se non ricavabile lascia vuoto e aggiungi nota)
   - Se il video contiene capitoli multipli, crea un esercizio per capitolo; se e' un flusso continuo, segmenta per esercizio visibile.
3. Se il video non ha capitoli, usa trascrizione/descrizione + visione euristiche per stimare intervalli. Documenta l'incertezza in `Note`.

### 2C. Instagram (post/reel)
1. Risolvi con `yt-dlp` (supporta instagram):
   ```python
   opts = {"quiet": True, "skip_download": True}
   with yt_dlp.YoutubeDL(opts) as ydl:
       info = ydl.extract_info(instagram_url, download=False)
   ```
   Se bloccato, usa `WebFetch` sulla pagina e estrai descrizione/hashtag.
2. Estrai esercizi dalla caption/descrizione o dalla sequenza visiva descritta.
3. `VideoURL` = link Instagram originale fornito dall'utente
4. `TimestampStart`/`TimestampFinish` = secondi nel reel dove appare l'esercizio (se reel unico con piu' esercizi, stima equamente: es. reel 30s con 3 esercizi -> 0-10, 10-20, 20-30). Se non stimabile, lascia vuoto.

### 3. Genera il CSV
```python
from csv_utils import scrivi_esercizi_csv, parse_esercizi_csv
esercizi = [
    {"nome": "...", "spiegazione": "...", "note": "...", "ripetizioni": "3x12", "recupero": "60 SEC",
     "gruppo": "Attivazione", "video_url": "https://...", "ts_start": 12.0, "ts_finish": 25.0,
     "frame_start": None, "frame_finish": None},
    # ...
]
scrivi_esercizi_csv(esercizi, "scheda_iniziale.csv")
# verifica
parse_esercizi_csv("scheda_iniziale.csv")
```
Per creare direttamente il bundle `.scheda`:
```python
from scheda_file import salva_scheda
salva_scheda(esercizi, "scheda_iniziale.scheda")
```

### 4. Controlli finali
- Verifica che `Nome` sia univoco per slug (evita duplicati che causano `_2` automatico). Se duplicato inevitabile, differenzia (es. "Squat - variante 1").
- Se fonte video, assicurati che ogni riga con `VideoURL` abbia almeno un timestamp o una nota sul tempo.
- Stampa riepilogo: numero esercizi, sorgente, quanti con video/timestamp, file generato.

## Esempi di invocazione
- "creami un allenamento con 5 esercizi per rinforzare l'arcata plantare" -> 5 righe, Gruppo=Attivazione/Rinforzo, nessun VideoURL
- "https://www.youtube.com/watch?v=abc123 fai 4 esercizi" -> 4 righe con stesso VideoURL e timestamp diversi
- "https://www.youtube.com/playlist?list=PL... seleziona solo esercizi per core" -> filtra chapters/titoli per pertinenza
- "https://www.instagram.com/reel/XYZ/" -> esercizi dalla caption con VideoURL=link Instagram

## Note
- Non scaricare video completi; usa solo `skip_download` + metadati.
- Se la playlist e' lunga, limita a max 12 esercizi o chiedi conferma.
- Chiedi chiarimenti solo se obiettivo/numero esercizi e' ambiguo; altrimenti procedi con defaults ragionevoli.
