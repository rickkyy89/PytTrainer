# Contratto 01 — Transazioni, cronologia e salvataggio

## Scopo

Questo documento definisce il contratto tra il dominio della scheda e le UI
(Kivy oggi, eventuali UI future). Non contiene widget, eventi Kivy o dettagli
di layout. Una sessione di editing lavora su una sola copia locale del bundle e
usa Drive esclusivamente come destinazione di sincronizzazione.

## Stato della sessione

Una `EditSession` espone questi dati osservabili:

| Dato | Significato |
|---|---|
| `value` | Manifest, titolo e riferimenti ai media attualmente in memoria |
| `checkpoint` | Snapshot completo dell'ultimo salvataggio locale riuscito |
| `dirty` | `value` non equivalente a `checkpoint` |
| `local_revision` | Versione locale incrementata a ogni checkpoint riuscito |
| `sync_state` | `SYNCED`, `LOCAL_ONLY` oppure `CONFLICT` |
| `can_undo` / `can_redo` | Disponibilità delle rispettive pile |

`dirty` non descrive lo stato di Drive. Dopo un salvataggio locale riuscito è
La copia locale più recente è sempre quella rappresentata da `value` e dal
file bundle appena scritto; la copia Drive è sincronizzata soltanto dopo una
risposta positiva dell'upload. Un conflitto non viene risolto implicitamente:
lascia `sync_state=CONFLICT` e viene restituito alla UI.

Il checkpoint comprende tutti i dati necessari a ripristinare la scheda:
manifest, titolo e contenuti dei frame gestiti dalla sessione. I file di lavoro
temporanei delle anteprime non fanno parte del checkpoint.

## Comandi e cronologia

Ogni modifica confermata viene rappresentata da un comando con questo contratto
logico:

```text
Command
  apply(state) -> None
  undo(state) -> None
  redo(state) -> None       # di default equivalente a apply
  release() -> None         # rilascia risorse possedute dal comando
```

Il contratto non impone come lo stato venga copiato. Per testo e struttura il
comando può conservare valori precedenti/successivi; per i media può conservare
snapshot di file tramite un adattatore. In entrambi i casi `apply`, `undo` e
`redo` sono atomici dal punto di vista della sessione: se falliscono, lo stato
precedente deve restare invariato e il comando non entra nella cronologia.

La sessione mantiene:

- `undo_stack`: massimo 20 comandi, dal più vecchio al più recente;
- `redo_stack`: comandi annullati, dal più recente al più vecchio.

Regole:

1. `execute(command)` applica il comando, accoda una sola azione in
   `undo_stack` e svuota interamente `redo_stack`.
2. Se l'applicazione fallisce, entrambe le pile e lo stato restano invariati.
3. `undo()` annulla l'ultimo comando, lo sposta in `redo_stack` e non crea una
   nuova azione.
4. `redo()` riapplica l'ultimo comando annullato, lo riporta in `undo_stack` e
   non crea una nuova azione.
5. Una nuova modifica dopo `undo()` elimina il ramo redo e libera le risorse
   dei comandi scartati.
6. Quando il ventunesimo comando entra nella pila, viene espulso il comando più
   vecchio e viene chiamato `release()` su di esso. Il limite vale insieme per
   modifiche testuali, strutturali e media.
7. Un comando no-op non viene registrato (per esempio spostare un esercizio già
   nella posizione richiesta o confermare lo stesso testo).

L'editor costruisce comandi per `aggiorna`, `aggiungi`, `rimuovi`, riordino,
cambio gruppo e importazione. Il flusso media usa la stessa sessione e non una
seconda cronologia: URL, timestamp, sostituzione/importazione frame e crop
devono quindi essere comandi della stessa interfaccia. La gestione concreta
della proprietà e del cleanup degli snapshot media è definita nel ticket 04.

## Ciclo di salvataggio

### Salva locale

`save_local()` acquisisce prima il valore dell'eventuale campo attivo, valida il
manifest e scrive il bundle in modo atomico. Solo dopo il successo:

- sostituisce `checkpoint` con uno snapshot dello stato scritto;
- azzera `undo_stack` e `redo_stack`, chiamando `release()` sui loro comandi;
- imposta `dirty=False`, incrementa `local_revision` e imposta
  `sync_state=LOCAL_ONLY` se Drive non è già stato aggiornato.

Se la scrittura o la validazione fallisce, stato, checkpoint e cronologia non
cambiano.

### Salva su Drive

`save_drive()` esegue sempre `save_local()` prima dell'upload. Il checkpoint
locale resta valido anche se l'upload fallisce. Gli esiti sono:

- upload riuscito: `dirty=False`, `sync_state=SYNCED`;
- rete/errore transitorio: `dirty=False`, `sync_state=LOCAL_ONLY`, errore
  mostrabile e possibilità di ritentare l'upload;
- conflitto Drive: `dirty=False`, `sync_state=CONFLICT`, conflitto esposto alla
  UI senza scegliere una versione automaticamente.

Un retry dopo `LOCAL_ONLY` non deve riscrivere la cronologia: deve caricare il
checkpoint locale già riuscito. Una risoluzione di conflitto che accetta la
versione locale può riportare lo stato a `SYNCED`; quella remota sostituisce
`value` e `checkpoint` con il download remoto e svuota la cronologia.

## Uscita e ripristino

- `discard()` ripristina `checkpoint`, elimina ogni modifica in memoria, libera
  le risorse delle due pile e lascia `dirty=False`. Non esegue upload.
- `restore_checkpoint()` ha la stessa operazione di ripristino ma non chiude la
  sessione; serve a implementare Scarta e a ripartire dal checkpoint locale.
- Se `dirty=False`, Indietro/chiusura può uscire senza dialogo.
- Se `dirty=True`, la UI deve offrire esclusivamente Salva, Scarta e Resta.
  Resta non modifica nulla; Salva segue una delle due operazioni sopra;
  Scarta esegue `restore_checkpoint()` prima di uscire.
- `LOCAL_ONLY` senza `dirty` non richiede di scartare dati: la UI deve offrire
  anche il retry di Drive e indicare che il checkpoint locale è più recente.
- Un errore di salvataggio non autorizza l'uscita automatica e non cambia il
  valore del campo attivo.

## Interfaccia minima condivisa

L'implementazione può chiamarsi `EditSession` o essere incorporata nel
controller, ma deve esporre almeno:

```text
execute(command)
undo() -> bool
redo() -> bool
save_local() -> SaveResult
save_drive() -> SaveResult
restore_checkpoint() -> None
discard() -> None
state -> value, dirty, local_revision, sync_state, can_undo, can_redo
```

`SaveResult` distingue `LOCAL_SAVED`, `DRIVE_SYNCED`, `DRIVE_FAILED` e
`CONFLICT`, includendo l'eccezione o il conflitto senza nasconderlo. La UI
chiama questi metodi e osserva lo stato; non manipola pile, snapshot o file
direttamente.

## Matrice di test e failure mode

| Caso | Aspettativa verificabile |
|---|---|
| modifica, undo, redo | valore esatto iniziale/modificato e pile corrette |
| nuova modifica dopo undo | redo vuoto, nuovo comando mantenuto |
| 21 modifiche | solo le ultime 20, primo comando rilasciato |
| comando fallito | valore e pile identici a prima |
| testo, struttura e media misti | una sola sequenza ordinata e undo inverso |
| salvataggio locale riuscito | checkpoint aggiornato, dirty falso, pile vuote |
| salvataggio locale fallito | checkpoint, dirty e cronologia invariati |
| upload fallito dopo locale | dirty falso, `LOCAL_ONLY`, retry possibile |
| conflitto Drive | `CONFLICT`, nessuna scelta automatica |
| restore/discard | dati e file uguali al checkpoint, nessun upload |
| campo attivo | il valore confermato è incluso prima del salvataggio |
| frame mancante o snapshot illeggibile | operazione atomica, nessun file orfano |

Questi test devono usare il filesystem temporaneo e fake per il trasporto Drive;
non devono importare Kivy né verificare dettagli grafici.
