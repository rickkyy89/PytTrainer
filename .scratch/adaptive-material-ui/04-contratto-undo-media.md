# Contratto 04 — Undo transazionale dei media

## Confine della transazione

La cronologia dei media è la stessa cronologia dell'editor: non esiste una pila
separata entrando nella schermata Video/Frame. Ogni azione che modifica il
manifest o un'immagine persistente produce un solo comando. Le anteprime di
crop e scrub sono invece temporanee e non producono comandi.

Le operazioni sono:

- URL video e timestamp START/FINISH;
- estrazione o sostituzione di uno o entrambi i frame;
- importazione di un'immagine utente;
- crop di un frame e ripristino dell'originale.

La ricerca, la lettura della durata, la selezione dei risultati e la riproduzione
del video non modificano la scheda e non entrano nella cronologia.

## Snapshot e ownership

Un `MediaSnapshot` contiene:

```text
manifest: copia profonda dei campi media dell'esercizio
files: { percorso_relativo_bundle: contenuto_binario }
```

I percorsi sono relativi alla cartella di lavoro del bundle, non assoluti e non
fuori dal bundle. Sono inclusi i frame START/FINISH e i backup `_orig.jpg`
presenti; sono esclusi `_crop_preview_*`, `_scrub_preview_*` e altri file
temporanei.

Il comando media possiede lo snapshot `before` e `after` fino a quando viene
espulso dalla cronologia. Il comando è responsabile di liberarli nel suo
`release()`. Il checkpoint locale possiede invece lo snapshot completo corrente
fino al prossimo checkpoint o alla chiusura della sessione. Undo/redo non
trasferiscono la proprietà al controller UI.

Il limite di 20 comandi è globale per editor e media. Espellere un comando dalla
pila undo, scartare il ramo redo o azzerare la cronologia al salvataggio chiama
`release()` e rimuove immediatamente i relativi snapshot. Non si conservano
backup numerati per ogni modifica e non si duplica un file se il suo contenuto
è già identico nello snapshot precedente.

## Applicazione atomica

Ogni operazione media segue questa sequenza:

1. Validare suffisso, timestamp, percorso e file sorgente senza cambiare nulla.
2. Creare lo snapshot `before` dei campi e dei file coinvolti.
3. Eseguire l'operazione in una directory temporanea dello stesso filesystem.
   Un crop scrive un nuovo file temporaneo; un'importazione converte in un
   percorso temporaneo; un'estrazione produce i due frame temporanei.
4. Verificare che ogni output sia leggibile e che i due frame, quando richiesti,
   siano presenti.
5. Sostituire i file destinazione con `os.replace` e aggiornare il manifest
   solo dopo che tutti gli output sono pronti.
6. Creare lo snapshot `after`, registrare un solo comando e notificare l'editor.

Se un qualunque passaggio fallisce, eliminare temporanei e output parziali,
ripristinare i file preesistenti e lasciare manifest, anteprime e cronologia
esattamente come prima. Un errore dopo la sostituzione di START ma prima di
FINISH non può lasciare un esercizio mezzo aggiornato.

## Semantica delle operazioni

### URL e timestamp

Il comando conserva i valori precedenti e successivi di `video_url`, `ts_start`
e `ts_finish`. Le euristiche applicate quando si seleziona un video fanno parte
dello stesso comando della selezione, non di tre azioni invisibili separate.

### Frame estratti e importati

I nuovi file hanno i nomi canonici già previsti dal bundle. Il comando conserva
il contenuto precedente anche quando il percorso resta uguale, quindi Undo
ripristina il byte stream corretto, non soltanto il riferimento nel manifest.
Se il frame precedente non esiste, Undo rimuove il nuovo file e il riferimento;
Redo lo ricrea dal proprio snapshot `after`.

### Crop e backup

Il primo crop di un frame crea `<frame>_orig.jpg`, che entra nello snapshot e
nel bundle. Crop successivi aggiornano il frame ma non sovrascrivono l'originale
di backup. Undo di un crop ripristina contenuto e presenza/assenza del backup
come erano prima; Undo dell'intera catena può quindi arrivare allo stato senza
backup. `ripristina` è a sua volta un comando, non una mutazione speciale.

## Undo, redo e checkpoint

Il comando media usa lo stesso contratto del ticket 01: Undo sposta il comando
nella pila redo, Redo lo riapplica, una nuova modifica elimina il ramo redo e
il ventunesimo comando libera il più vecchio. Applicare uno snapshot deve essere
atomico anche durante Undo/Redo: se il filesystem non consente la sostituzione,
il comando resta nella pila originale e lo stato precedente viene ricostruito.

Il salvataggio locale scrive manifest, frame e backup atomically, poi cattura il
nuovo checkpoint e libera tutte le pile. Un errore di scrittura non libera nulla.
Scarta e `restore_checkpoint()` ripristinano anche i byte dei frame senza
upload. Chiudere o lasciare Media senza salvare non elimina la cronologia:
la sessione editor resta la proprietaria e Back dell'editor decide Salva,
Scarta o Resta. Riaprire Media sullo stesso esercizio vede lo stato live e la
stessa cronologia; aprire nuovamente il bundle dopo chiusura vede solo l'ultimo
checkpoint scritto.

## Interfaccia con il flusso media

`MediaFlowController` non decide dove collocare la cronologia. Riceve dal
controller editor un sink transazionale, concettualmente:

```text
execute_media(mutator, file_effects) -> result
```

Il sink acquisisce snapshot, coordina filesystem e manifest e inoltra l'azione
alla cronologia condivisa. Il controller media può continuare a esporre le API
attuali (`url_manuale`, `imposta_timestamp`, `ritaglia`, `importa_immagine`,
`estrai`), ma non deve più mutare direttamente il dict senza passare dal sink.
Le callback `on_change` restano solo per aggiornare la UI e non sono il confine
di atomicità.

## Test e failure mode

| Scenario | Verifica |
|---|---|
| URL/timestamp | Undo/redo ripristina valori e produce una sola azione |
| crop singolo e ripetuto | contenuto frame e backup esatti a ogni passaggio |
| import sopra frame esistente | Undo ripristina i byte originali |
| frame inizialmente mancante | Undo elimina file e riferimento; Redo li ricrea |
| errore tra START e FINISH | nessun output parziale, manifest invariato |
| sorgente immagine non leggibile | nessuna modifica e nessuna azione |
| 21 azioni miste editor/media | pila globale di 20 e snapshot espulso liberato |
| modifica dopo Undo | ramo redo e relativi file temporanei eliminati |
| salvataggio locale | pile vuote e checkpoint completo di frame/backup |
| Scarta/riapertura Media | byte e manifest uguali al checkpoint |
| sostituzione filesystem fallita | stato precedente intatto, errore esposto |

I test usano `tmp_path`, immagini con contenuti distinguibili e un fake per
estrazione/upload. Verificano i byte con `read_bytes()`, non solo l'esistenza
dei percorsi, e non importano Kivy.
