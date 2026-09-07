# pyTrainer Exercise Library v0.2

MVP locale per raccogliere video di esercizi, deduplicarli in SQLite, ricevere analisi strutturate e generare CSV compatibili con pyTrainer.

## Cosa fa già

- database SQLite locale;
- aggiunta di URL YouTube / Instagram / Facebook / web;
- import di una playlist YouTube senza scaricare i video;
- deduplica dei video YouTube tramite ID canonico;
- download esplicito di singoli video YouTube, fino a 720p, per l'analisi AI;
- coda JSON per il passaggio a un analizzatore AI;
- import di un risultato AI con più esercizi per video;
- categorie, sottocategorie, confidence e tag;
- export CSV canonico a 11 colonne per pyTrainer.

## Setup Windows

```powershell
cd pytrainer-library-v0.1
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python tools\collector.py init
```

## 1. Aggiungere un URL

Solo inbox, senza dipendere dal fatto che yt-dlp riesca ad aprirlo:

```powershell
python tools\collector.py add "https://www.instagram.com/reel/..."
```

Per provare anche a recuperare titolo/durata/autore:

```powershell
python tools\collector.py add "https://www.youtube.com/watch?v=..." --metadata
```

## 2. Importare una playlist YouTube

```powershell
python tools\collector.py playlist "https://www.youtube.com/playlist?list=..."
```

Il comando usa la modalità flat: recupera l'elenco senza scaricare tutti i video.

## 3. Vedere la inbox

```powershell
python tools\collector.py list --status NEW
```

## 4. Preparare un video per l'analisi AI

Il download e' sempre esplicito: non viene avviato durante l'import della playlist.
I file sono salvati in `videos/youtube/` con un nome stabile basato su ID e titolo. Al
termine il video passa a `READY_FOR_ANALYSIS`; se il file locale e' gia' valido non
viene riscaricato, salvo `--force`.

```powershell
python tools\video_prepare.py 59
python tools\video_prepare.py 6 8 9 13
python tools\video_prepare.py --list-ready
python tools\video_prepare.py 59 --force
python tools\video_prepare.py 59 --discard
```

I video senza metadata completi vengono comunque tentati tramite URL canonico. Se il
download fallisce, il loro stato viene impostato a `ERROR` senza interrompere gli altri ID.

Il CSV non viene generato durante analisi o import: e' un export esplicito, da creare
solo quando serve comporre una scheda pyTrainer.

Dopo l'import dell'analisi, `--discard` elimina solo il download locale: il record,
l'URL, i risultati JSON e gli esercizi in SQLite restano disponibili.

## 5. Preparare il bridge per l'analisi AI

```powershell
python tools\analysis_io.py queue 1
```

Genera:

```text
analysis/pending/video_0001.json
```

Il JSON contiene metadata del video e lo schema esatto richiesto per gli esercizi rilevati.

## 6. Importare il risultato dell'analisi

Un risultato ha questa forma:

```json
{
  "video_id": 1,
  "exercises": [
    {
      "name": "Uscita bassa dopo trasmissione laterale",
      "category": "Portiere",
      "subcategory": "Situazionale / Uscita",
      "description": "Il portiere segue la circolazione e interviene in uscita bassa sull'attaccante.",
      "notes": "Curare tempo di uscita e posizione iniziale.",
      "repetitions": "",
      "recovery": "",
      "timestamp_start": 42.5,
      "timestamp_finish": 58.2,
      "confidence": "HIGH",
      "tags": ["1 contro 1", "calcio a 5"]
    }
  ]
}
```

Poi:

```powershell
python tools\analysis_io.py import analysis\results\video_0001.json
```

## 7. Esportare per pyTrainer

Tutti gli esercizi:

```powershell
python tools\export_pytrainer.py
```

Per categoria:

```powershell
python tools\export_pytrainer.py --category "Portiere"
```

Per categoria + sottocategoria:

```powershell
python tools\export_pytrainer.py --category "Portiere" --subcategory "Situazionale / Uscita"
```

Per un solo video analizzato:

```powershell
python tools\export_pytrainer.py --video-id 59 --output exports\video_0059.csv
python tools\export_pytrainer.py --exercise-id 2 --exercise-id 4 --output exports\selezione.csv
```

I CSV vengono scritti in `exports/` con UTF-8 BOM, adatto anche all'apertura diretta in Excel.

## Analisi video con Scrutatore

Le analisi visive vengono delegate al subagente OpenCode `scrutatore`, indipendentemente
dal modello scelto per l'agente `build`. Il modello primario e' `openai/gpt-5.6-luna`;
il fallback e' `opencode-go/qwen3.8-flash`.

```text
/analizza-video 6
```

Scrutatore prepara i frame e produce solo JSON. L'agente principale valida e importa il
risultato; l'export CSV resta un'operazione esplicita. Quando almeno un esercizio ha
confidence inferiore a `0.75`, l'agente build riesamina gli stessi artefatti con il
proprio modello e salva un secondo JSON per il confronto. Se il dubbio persiste, il
risultato resta fuori dal database fino alla revisione dell'allenatore.

I tag vengono normalizzati da `tools/tag_policy.py`: sinonimi e traduzioni vengono
ricondotti a forme italiane canoniche, i tag generici sono rimossi e categoria o
sottocategoria non vengono duplicate. Per revisionare gli artefatti esistenti:

```powershell
python tools\tag_policy.py --apply
```

## Flusso target

```text
link / playlist
      ↓
collector
      ↓
SQLite (NEW)
      ↓
preparazione video
      ↓
analisi ChatGPT
      ↓
0..N esercizi
      ↓
SQLite (ANALYZED)
      ↓
export CSV
      ↓
pyTrainer
```

## Stati video

- `NEW`: raccolto ma non preparato;
- `DOWNLOADED`: download locale completato ma non ancora pronto;
- `READY_FOR_ANALYSIS`: file locale valido e pronto per il passaggio successivo;
- `ANALYZED`: esercizi importati nel database;
- `ERROR`: errore operativo da riesaminare.

## Limiti attuali

La v0.2 non include ancora cookie/browser, segmentazione, scene detection, clip,
estrazione frame o analisi AI automatica.
