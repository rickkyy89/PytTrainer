# Proposta di miglioramenti — Workout Sheet Automator (PytTrainer)

Documento di lavoro con le considerazioni emerse durante un utilizzo reale del
software (generazione di una scheda da 9 esercizi in modalità automatica, CSV
→ Google Doc). Da passare a Claude Code (o a chiunque implementi) come base
per lo sviluppo.

## 1. Problemi riscontrati nell'uso reale

### 1.1 Generazione del documento non riprendibile

`create_workout_document()` in `google_docs_helper.py` è un blocco monolitico:
crea il documento e itera su tutti gli esercizi in un'unica funzione, senza
checkpoint intermedi. Se l'esecuzione si interrompe a metà (errore di rete,
timeout dell'ambiente che esegue lo script, rate limit delle API Google),
il risultato è un Google Doc parziale e orfano su Drive, e bisogna ripartire
da zero rigenerando tutto (inclusi gli esercizi già scritti correttamente).
Durante il test è successo 3 volte, con conseguente pulizia manuale dei
documenti orfani via Drive API.

### 1.2 Nessuna persistenza della scelta di video/timestamp

Il CSV degli esercizi (`Nome,Spiegazione,Note,Ripetizioni,Recupero`) contiene
solo il testo. Non c'è alcuna traccia di:

- quale video YouTube è stato scelto per ciascun esercizio;
- quali timestamp sono stati usati per i frame START/FINISH;
- dove sono salvati i frame estratti.

Conseguenza: una volta generato il documento, quella decisione è persa. Per
sostituire un video non pertinente o correggere un timestamp bisogna rifare
la ricerca da capo, senza alcuna garanzia di ripescare lo stesso video, e non
esiste un modo per aggiornare solo quell'esercizio nel documento già creato.

### 1.3 Euristica di ricerca video fragile, nessun controllo umano nel flusso automatico

`search_youtube()` + "primo risultato da cui riesco a estrarre due frame
validi" è un'euristica debole basata solo sulla ricercabilità tecnica del
frame, non sulla pertinenza del contenuto. Esempio reale riscontrato: per
"Short Foot (Piede Corto)" il primo risultato utilizzabile (dopo che il primo
video in assoluto risultava non disponibile) era un video di allenamento di
boxe di Anthony Joshua, agganciato solo per la parola "Short" nel titolo. I
frame erano tecnicamente validi (immagini non vuote, estratte correttamente)
ma completamente sbagliati nel merito. CLAUDE.md indica esplicitamente di non
usare l'interfaccia Streamlit per l'uso automatico, quindi in quel flusso non
c'è alcun checkpoint per intercettare questo tipo di errore prima che finisca
nel documento finale.

### 1.4 Nessun concetto di sottogruppo/sezione

L'utente organizza naturalmente gli esercizi in fasi (es. Stretching
Iniziale, Attivazione, Rinforzo Muscolare, Stretching Finale/Defaticamento).
Il generatore attuale tratta `exercises` come lista piatta e inserisce
un'interruzione di pagina ogni 3 esercizi (`(indice + 1) % 3 == 0`), senza
alcuna intestazione di sezione né relazione con la struttura logica della
scheda. Nell'uso reale questa struttura è andata persa: gli esercizi sono
finiti nel documento in un unico blocco ordinato, senza titoli di sezione.

### 1.5 OAuth pensato solo per esecuzione locale con browser

`get_credentials()` in caso di primo login chiama
`flow.run_local_server(port=0)`, che presuppone che lo script giri sulla
macchina dell'utente con un browser disponibile e una porta locale
raggiungibile. In un contesto di esecuzione remota/headless (agente, CI,
sandbox) questo non funziona: bisogna costruire manualmente l'URL di
autorizzazione con `flow.authorization_url()`, far incollare all'utente
l'URL di redirect (o il solo `code`) e completare lo scambio con
`flow.fetch_token(code=...)`. Utile prevedere questo path come alternativa
di libreria, non da reinventare ogni volta.

## 2. Direzione proposta

Il pezzo architetturale che sblocca la maggior parte dei problemi sopra è
trasformare il CSV da file "usa e getta" a **manifest persistente**:
un CSV esteso che funge da salva/carica per l'intera scheda, comprese le
scelte di video e timestamp. Su questa base si costruiscono le altre
funzionalità.

### 2.1 Schema CSV esteso (decisione presa: CSV, non JSON)

Aggiungere colonne opzionali (retrocompatibili: se assenti o vuote, il
comportamento resta quello attuale — ricerca automatica del video):

| Colonna | Obbligatoria | Descrizione |
|---|---|---|
| `Nome` | sì (esistente) | Nome esercizio |
| `Spiegazione` | sì (esistente) | Spiegazione tecnica |
| `Note` | sì (esistente) | Note di esecuzione |
| `Ripetizioni` | sì (esistente) | Es. `3x12` |
| `Recupero` | sì (esistente) | Es. `90 SEC` |
| `Gruppo` | no | Nome della sezione/sottogruppo (es. `Stretching Iniziale`). Se assente, tutti gli esercizi finiscono in un gruppo implicito unico. |
| `VideoURL` | no | URL YouTube scelto/forzato. Se presente, salta `search_youtube()` e usa direttamente questo video. |
| `TimestampStart` | no | Secondo del frame START. Se assente, si applica l'euristica attuale (10% della durata). |
| `TimestampFinish` | no | Secondo del frame FINISH. Se assente, euristica attuale (50% della durata). |
| `FrameStartPath` / `FrameFinishPath` | no | Percorso dei frame già estratti in una run precedente. Se presenti e i file esistono ancora, salta la ri-estrazione. |

Il file CSV, una volta processato, va **riscritto arricchito** con i valori
usati (video scelto, timestamp, path dei frame), così diventa il "salvataggio"
della scheda: riaprendolo e ri-lanciando la generazione si ottiene lo stesso
risultato (idempotenza), e modificando a mano una singola cella (es.
`VideoURL` o i timestamp) si può correggere un solo esercizio.

### 2.2 Sottogruppi con titolo di sezione

Modificare `create_workout_document()` (o aggiungere una variante) perché
accetti gli esercizi raggruppati per `Gruppo` (deducibile dalla colonna CSV,
mantenendo l'ordine di prima apparizione) e per ciascun gruppo:

- inserisca un paragrafo di intestazione con il nome del gruppo (stile
  distinto da quello del titolo generale e da quello del nome esercizio);
- valuti l'interruzione di pagina in base al cambio di gruppo (o comunque in
  modo configurabile), non più con una regola cieca ogni 3 esercizi.

### 2.3 Sostituzione mirata di video/frame

Nuova funzione, ad es. `update_exercise_media(doc_id, exercise_index, ...)`
in `google_docs_helper.py`, che:

- accetta un nuovo `VideoURL` e/o nuovi timestamp per un esercizio già
  presente nel documento;
- ri-estrae i frame necessari (riusando `extract_start_finish_frames`);
- individua nel documento esistente la tabella corrispondente a
  quell'esercizio (richiede di **tracciare** l'indice/ID della tabella per
  esercizio in un manifest di stato, vedi 2.4) e sostituisce solo le due
  immagini inline, senza rigenerare l'intero documento.

Per rendere possibile questa individuazione servono degli ancoraggi stabili:
la soluzione più semplice è mantenere, oltre al CSV, un piccolo file di stato
per documento (es. `<nome_scheda>.state.json`) con la mappa
`indice_esercizio → tableStartIndex` (o un bookmark/named range di Google
Docs, se si vuole evitare di ricalcolare gli indici a ogni modifica — da
valutare in fase di implementazione quale sia più robusto rispetto a
inserimenti/cancellazioni successive che spostano gli indici).

### 2.4 Generazione resumibile

Rendere `create_workout_document()` capace di riprendere da dove si era
interrotta, invece di richiedere di rigenerare tutto da capo:

- persistere uno stato minimo (`doc_id`, elenco esercizi già inseriti con
  relativo indice/tabella) su un file locale associato alla scheda;
- se lo stato esiste già per quella scheda, riusare il `doc_id` esistente e
  aggiungere solo gli esercizi mancanti, invece di creare un nuovo documento;
- eventualmente esporre un parametro per processare un esercizio alla volta
  (utile anche per contesti con limiti di tempo per singola chiamata, come
  quello in cui è stato fatto questo test), oltre alla modalità "tutto in
  un colpo" per l'uso interattivo/Streamlit.

Questo stato è lo stesso meccanismo utile anche per il punto 2.3 (sapere
quale tabella corrisponde a quale esercizio).

### 2.5 Filtro di rilevanza video

Prima di accettare il primo risultato "tecnicamente estraibile" da
`search_youtube()`, aggiungere un controllo leggero di pertinenza, ad
esempio:

- normalizzare nome esercizio e titolo video (minuscolo, rimozione
  punteggiatura/stopword) e richiedere una sovrapposizione minima di parole
  chiave prima di tentare l'estrazione dei frame;
- scartare video palesemente fuori contesto per durata (es. troppo lunghi/
  corti rispetto a un tutorial tipico) come segnale aggiuntivo, non unico;
- in alternativa o in aggiunta, nel flusso automatico loggare chiaramente
  quali video sono stati scartati e perché, e quale è stato scelto, così chi
  supervisiona (umano o agente) può verificare rapidamente senza dover
  ispezionare ogni frame a mano come fatto in questo test.

### 2.6 OAuth per esecuzione headless/remota

Aggiungere in `google_docs_helper.get_credentials()` (o in una funzione
dedicata, es. `get_credentials_manual_flow()`) il path alternativo già
sperimentato in questo test:

```python
flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
flow.redirect_uri = "http://localhost"
auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
# l'utente apre auth_url, autorizza, e incolla il code (o l'URL di redirect fallito)
flow.fetch_token(code=code)
creds = flow.credentials
```

Da documentare in CLAUDE.md come alternativa esplicita a
`run_local_server()` quando lo script non gira sulla macchina dell'utente
(nessun browser/display disponibile localmente).

## 3. Note di compatibilità

Tutte le modifiche proposte sono pensate per essere **additive**: un CSV nel
formato attuale (solo le 5 colonne obbligatorie) deve continuare a funzionare
esattamente come oggi, con ricerca automatica del video e frame euristici.
Le nuove colonne e funzioni sono opt-in.
