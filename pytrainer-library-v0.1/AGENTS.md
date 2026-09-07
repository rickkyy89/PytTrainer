# pyTrainer Library — Agent Instructions

## 1. Scopo del progetto

`pytrainer-library` è una libreria intelligente di esercizi di allenamento, separata ma complementare a `pyTrainer`.

L'utente è un allenatore di portieri di calcio a 5 femminile amatoriale. Salva nel tempo molti video di esercizi provenienti soprattutto da:

* playlist YouTube;
* singoli video YouTube;
* Instagram;
* Facebook;
* più raramente video personali/locali.

Il problema da risolvere è trasformare questi video, oggi difficili da ritrovare e riutilizzare, in una libreria strutturata e interrogabile.

Il sistema deve:

1. raccogliere URL e playlist;
2. evitare duplicati;
3. scaricare/preparare i video quando necessario;
4. analizzare visivamente il contenuto;
5. riconoscere uno o più esercizi presenti nello stesso video;
6. descriverli in modo breve e utile;
7. classificarli;
8. individuare un intervallo temporale rappresentativo;
9. salvare tutto in SQLite;
10. permettere ricerca e riutilizzo;
11. esportare CSV direttamente importabili in `pyTrainer`.

Il valore principale del progetto NON è semplicemente convertire video in CSV.

Il valore è creare nel tempo una **memoria esterna strutturata degli esercizi dell'allenatore**.

---

# 2. Relazione con pyTrainer

`pyTrainer` è già funzionante e NON deve essere riscritto.

La libreria deve rimanere un progetto separato.

Pipeline concettuale:

video / playlist
→ pytrainer-library
→ SQLite
→ ricerca/composizione
→ CSV
→ pyTrainer
→ `.scheda`

Il CSV è un formato di scambio verso pyTrainer.

NON usare il CSV come database principale della libreria.

---

# 3. Formato CSV pyTrainer

pyTrainer usa questo ordine canonico di 11 colonne:

Nome,Spiegazione,Note,Ripetizioni,Recupero,Gruppo,VideoURL,TimestampStart,TimestampFinish,FrameStartPath,FrameFinishPath

Le prime cinque sono obbligatorie per il parser:

* Nome
* Spiegazione
* Note
* Ripetizioni
* Recupero

Le altre sono opzionali:

* Gruppo
* VideoURL
* TimestampStart
* TimestampFinish
* FrameStartPath
* FrameFinishPath

Per gli esercizi provenienti dalla library:

* `Nome`: nome breve, specifico e distinto;
* `Spiegazione`: descrizione sintetica dell'esecuzione;
* `Note`: solo dettagli tecnici, errori, sicurezza o indicazioni importanti;
* `Ripetizioni`: può rimanere vuoto;
* `Recupero`: può rimanere vuoto;
* `Gruppo`: derivato dalla classificazione;
* `VideoURL`: URL originale;
* `TimestampStart`: in secondi, decimali ammessi;
* `TimestampFinish`: in secondi, decimali ammessi;
* `FrameStartPath`: normalmente vuoto;
* `FrameFinishPath`: normalmente vuoto.

NON inventare mai percorsi frame.

---

# 4. Principi architetturali

## 4.1 SQLite è la fonte di verità

Usare SQLite per:

* video;
* collections/playlist;
* esercizi;
* categorie;
* tag;
* stato dell'analisi;
* provenienza;
* timestamp;
* confidenza;
* metadata.

Uno stesso video può contenere N esercizi.

Un esercizio appartiene a un video sorgente.

Uno stesso video può appartenere a più collection.

---

## 4.2 Separare codice deterministico e AI

Il modello AI NON deve modificare direttamente SQLite.

Pipeline obbligatoria:

video
→ preprocessing deterministico
→ input AI
→ JSON strutturato
→ validazione Python
→ SQLite

Il modello produce dati.

Il codice Python:

* valida;
* normalizza;
* controlla range;
* gestisce duplicati;
* scrive nel database.

Questo principio va mantenuto anche nelle evoluzioni future.

---

## 4.3 Conservare sempre la provenienza

Ogni esercizio deve poter essere ricondotto a:

* video originale;
* URL;
* piattaforma;
* eventuale playlist/collection;
* titolo originale;
* autore/canale;
* timestamp.

Non perdere questa relazione durante export o riclassificazioni.

---

# 5. Collector

Il collector deve occuparsi solo della raccolta.

Non deve interpretare gli esercizi.

Deve supportare progressivamente:

* URL YouTube;
* playlist YouTube;
* Instagram URL;
* Facebook URL;
* file locali.

Per YouTube usare `yt-dlp`.

Una playlist deve poter essere enumerata senza scaricare automaticamente tutti i video.

Esempio:

playlist
→ 70 elementi
→ 67 nuovi
→ 3 già presenti

La deduplica deve utilizzare identificatori stabili quando disponibili.

Per YouTube preferire il video ID.

Non considerare duplicati due URL diversi soltanto perché hanno lo stesso titolo.

---

# 6. Instagram e Facebook

Non costruire inizialmente sistemi fragili basati su automazione completa del browser o scraping delle raccolte private.

Prima supportare bene:

URL ricevuto
→ inbox
→ metadata
→ eventuale download
→ analisi

In futuro si potrà aggiungere un sistema più automatico per importare elementi salvati.

L'affidabilità della library è più importante dell'automazione estrema.

---

# 7. Stati

Usare stati chiari.

Stato minimo consigliato:

NEW
DOWNLOADING
DOWNLOADED
PREPARING
READY_FOR_ANALYSIS
ANALYZING
ANALYZED
ERROR

Se è utile distinguere ulteriormente:

NEEDS_REVIEW

Non lasciare record indefinitamente in stati intermedi dopo un errore.

Conservare un messaggio di errore quando possibile.

---

# 8. Download video

Per l'analisi AI non serve massima qualità.

Preferire:

* formato facilmente gestibile;
* MP4 quando possibile;
* massimo circa 720p;
* dimensioni ragionevoli;
* qualità sufficiente per distinguere:

  * persone;
  * portiere;
  * pallone;
  * porta;
  * coni;
  * ostacoli;
  * attrezzi;
  * principali movimenti.

Usare nomi file stabili, idealmente:

<ID_DATABASE>_<slug_titolo>.mp4

Esempio:

59_sesion-porteros-jimbee-cartagena.mp4

Aggiornare `local_path`.

Non riscaricare file già validi salvo `--force`.

---

# 9. Preprocessing per AI

Non inviare automaticamente qualsiasi video lungo al modello senza preparazione.

Creare una cartella di lavoro per ogni video, per esempio:

analysis/work/59/
metadata.json
source.mp4
contact_sheet.jpg
frames/
transcript.txt
ai_input.json
ai_result.json

Il preprocessing può includere:

* metadata;
* titolo;
* descrizione;
* durata;
* fotogrammi distribuiti nel tempo;
* contact sheet;
* scene change detection;
* eventuale transcript/audio;
* frame aggiuntivi in zone interessanti.

Non complicare prematuramente il sistema.

Per la prima versione usare un sampling semplice e robusto.

Dopo aver osservato casi reali, migliorare il campionamento.

---

# 10. Analisi AI

Sono disponibili attraverso OpenCode più modelli, inclusi:

* Luna;
* Terra;
* Sol;
* Astra.

NON assumere a priori che un modello sia sempre migliore di un altro.

Prima costruire una pipeline indipendente dal modello.

Successivamente fare un benchmark sugli stessi video per confrontare:

* riconoscimento numero esercizi;
* qualità dei nomi;
* descrizione;
* classificazione;
* timestamp;
* capacità di comprendere esercizi situazionali;
* allucinazioni;
* velocità;
* costo/limiti se disponibili.

Il sistema deve poter scegliere il modello tramite configurazione.

Per il primo riferimento usare un modello disponibile capace di comprendere gli input visivi preparati.

---

# 11. Cosa deve fare l'AI

Per ogni video identificare zero, uno o più esercizi.

Un video fitness può contenere molti esercizi.

Un video situazionale può mostrare un singolo esercizio ripetuto molte volte.

In questo secondo caso creare normalmente UN SOLO esercizio, con un intervallo temporale rappresentativo.

L'AI deve produrre:

* nome;
* descrizione;
* note;
* categoria;
* sottocategoria;
* tag;
* timestamp start;
* timestamp finish;
* confidence.

Descrizioni brevi e concise.

Non scrivere trattati tecnici.

---

# 12. Interpretazione vs osservazione

Il modello può interpretare l'obiettivo dell'esercizio quando il contenuto lo supporta.

Esempio:

osservazione:
il portiere affronta un attaccante in 1vs1, poi recupera velocemente la porta e affronta una seconda conclusione.

interpretazione plausibile:
lavoro su uscita 1vs1 e recupero posizione.

Questa interpretazione è utile.

Se l'obiettivo non è chiaro, evitare di presentare supposizioni come fatti certi.

Usare `confidence`.

---

# 13. Confidence

Usare preferibilmente un valore numerico:

0.0 – 1.0

Interpretazione indicativa:

0.90–1.00 = molto alta
0.75–0.89 = alta
0.55–0.74 = media
<0.55 = bassa

La confidence deve riguardare soprattutto:

* identificazione dell'esercizio;
* classificazione;
* timestamp.

In futuro può essere usata per routing automatico:

analisi economica/rapida
→ confidence alta
→ salva

confidence bassa
→ seconda analisi con modello più capace
→ confronto
→ salva / NEEDS_REVIEW

Non implementare questo routing complesso finché la pipeline base non funziona bene.

---

# 14. JSON AI

Formato indicativo:

{
"video_id": 59,
"exercises": [
{
"name": "1 contro 1 con recupero posizione",
"description": "Il portiere affronta un 1 contro 1 e recupera rapidamente la posizione per una seconda conclusione.",
"notes": "Curare il tempo di uscita e la velocità di rientro in porta.",
"category": "Situazionale",
"subcategory": "1 contro 1",
"tags": [
"recupero posizione",
"doppio intervento",
"porta"
],
"timestamp_start": 18.5,
"timestamp_finish": 44.0,
"confidence": 0.91
}
]
}

Il parser deve verificare almeno:

* `exercises` è una lista;
* `name` non è vuoto;
* timestamp numerici o null;
* timestamp >= 0;
* finish > start quando entrambi presenti;
* timestamp <= durata video con una tolleranza ragionevole;
* confidence tra 0 e 1.

Il modello può restituire:

"exercises": []

se non identifica esercizi utili.

Non forzare sempre un risultato.

---

# 15. Tassonomia

NON definire una tassonomia enorme a tavolino.

La tassonomia deve emergere dai video reali.

Prima classificazione orientativa:

PORTIERE

* Tecnica
* Situazionale
* Preparazione

FITNESS

* Core / Addominali
* Equilibrio / Propriocezione
* Forza
* Mobilità
* Velocità
* Reattività
* Coordinazione

Possibili sottocategorie portiere:

* Presa
* Tuffo
* Spostamenti
* Gioco con i piedi
* Posizionamento
* Uscita
* 1 contro 1
* Secondo palo
* Copertura porta
* Transizione
* Reattività
* Velocità
* Coordinazione

Queste sono solo una base.

Non devono diventare vincoli rigidi.

Usare anche tag liberi.

Esempio:

category = Situazionale
subcategory = Posizionamento

tags =
secondo palo
recupero posizione
2 portieri
tiro ravvicinato
doppio intervento

La tassonomia potrà essere modificata senza rianalizzare i video.

---

# 16. Ricerca futura

La library deve permettere query del tipo:

* esercizi di uscita;
* esercizi per 1 contro 1;
* addominali;
* equilibrio;
* reattività;
* situazionali di posizionamento;
* esercizi con secondo palo;
* esercizi con 2 portieri;
* esercizi brevi;
* esercizi trovati in una specifica playlist.

Per questo conservare più informazioni di quelle strettamente necessarie al CSV.

---

# 17. Playlist pilota

Prima collection reale:

Nome:
Allenamento portiere

URL:

https://www.youtube.com/watch?v=tgHpr_z1-uI&list=PL-5igPyTc3VN6UwUaGRpV9VQaEPp14PcL

L'import effettuato ha prodotto circa 70 video.

La maggior parte dispone di:

* titolo;
* autore;
* durata;
* URL;
* YouTube ID.

Alcuni record possono essere video rimossi, privati o con metadata incompleti.

Il software deve gestirli senza crash.

---

# 18. Dataset iniziale di benchmark

Campione utile di video database:

6
8
9
13
15
19
24
41
47
52
57
59

Sono stati scelti perché includono casi differenti:

* tecnica portiere;
* 1vs1;
* agilità;
* esercizi multipli;
* tecnica + fisico;
* gioco coi piedi;
* secondo palo;
* circuiti;
* addominali;
* pliometria;
* sequenze tecniche;
* situazionali complessi.

NON analizzarli tutti subito.

Il primo test end-to-end deve essere il video #59.

---

# 19. Primo obiettivo concreto

Costruire una pipeline completa funzionante su UN video.

Video di riferimento:

ID database: 59

Contenuto indicativo:
sessione portieri Jimbee Cartagena, esercizio 1vs1 + recupero posizione e seconda conclusione.

Pipeline desiderata:

DB record #59
→ download
→ preprocessing
→ frame/contact sheet
→ AI
→ JSON
→ validazione
→ SQLite
→ export CSV pyTrainer

Non generalizzare prematuramente prima che questo ciclo funzioni.

---

# 20. CLI desiderata

La sintassi può evolvere, ma puntare verso qualcosa di semplice:

python tools/collector.py playlist "<url>"

python tools/collector.py add "<url>"

python tools/video_prepare.py 59

python tools/analyze.py 59

python tools/analyze.py 59 --model <model>

python tools/show.py video 59

python tools/show.py exercise <id>

python tools/list.py --status NEW

python tools/list.py --status READY_FOR_ANALYSIS

python tools/export_pytrainer.py --category "Situazionale"

python tools/export_pytrainer.py --ids 12 15 18

Preferire CLI componibili a una grande GUI.

OpenCode è il frontend principale durante lo sviluppo.

---

# 21. Esperienza utente desiderata

In futuro l'utente deve poter chiedere in linguaggio naturale:

"Importa questa playlist."

"Analizza i nuovi video."

"Cosa abbiamo per allenare le uscite?"

"Fammi vedere gli esercizi di posizionamento."

"Trova 5 esercizi situazionali per due portieri."

"Esporta questi in pyTrainer."

La complessità tecnica deve rimanere dietro le quinte.

---

# 22. Qualità del codice

Preferenze:

* Python semplice;
* dipendenze limitate;
* funzioni piccole;
* separazione netta delle responsabilità;
* logging utile;
* errori espliciti;
* test unitari;
* test senza dipendere realmente da YouTube quando possibile;
* mock dei processi esterni;
* migrazioni DB controllate;
* nessuna modifica distruttiva silenziosa.

Non introdurre framework pesanti senza una necessità concreta.

---

# 23. Regole per il database

Prima di cambiare lo schema:

1. ispezionare quello esistente;
2. verificare se il requisito può essere implementato senza migrazione;
3. se serve una migrazione, renderla ripetibile e sicura;
4. preservare i dati esistenti.

Non cancellare il DB per "ripartire puliti".

Non perdere i 70 video già importati.

---

# 24. Regole per file e cache

Separare:

* dati persistenti;
* cache;
* download ricreabili;
* risultati AI;
* export.

Un possibile layout:

database/
exercises.db

videos/
youtube/
instagram/
facebook/
local/

analysis/
work/
results/

exports/

inbox/

I file derivati devono poter essere ricreati senza distruggere il database.

---

# 25. Timestamp

Il timestamp deve indicare un tratto rappresentativo dell'esercizio.

Non è necessario includere tutte le ripetizioni.

Se lo stesso esercizio viene ripetuto per tre minuti, scegliere una sequenza chiara e rappresentativa.

Questi timestamp saranno utilizzati da pyTrainer per estrarre START e FINISH.

Quindi devono possibilmente contenere:

* una posizione iniziale leggibile;
* una posizione finale/intervento leggibile.

Se possibile evitare:

* dissolvenze;
* cambi camera;
* persone che coprono completamente il gesto;
* pause tra ripetizioni.

---

# 26. Output testuale

Nome, spiegazione e note devono essere in italiano anche se il video è in:

* inglese;
* portoghese;
* spagnolo;
* altre lingue.

Stile:

breve;
pratico;
da allenatore;
senza prosa superflua.

Esempio buono:

Nome:
1 contro 1 con recupero posizione

Spiegazione:
Il portiere affronta un 1 contro 1 e recupera rapidamente la posizione per una seconda conclusione.

Note:
Curare il tempo di uscita e il rientro rapido verso il centro porta.

Evitare descrizioni eccessivamente verbose.

Prima di salvare l'output, verificare il registro semantico di nomi, spiegazioni,
note, categorie e tag. Usare italiano tecnico breve; usare inglese solo se e' il
termine piu comune o piu conciso. Non lasciare traduzioni letterali o termini in
spagnolo/portoghese: per esempio `achicamento` diventa `uscita in chiusura`,
`reincorporazione` diventa `rialzata`, `queda lateral` diventa `tuffo laterale`
ed `espacate` diventa `parata in spaccata`.

---

# 27. Cosa NON fare

Non:

* riscrivere pyTrainer;
* creare una GUI complessa;
* rendere il CSV il database;
* lasciare che l'LLM scriva direttamente SQLite;
* analizzare 70 video prima di validare il metodo;
* creare decine di categorie rigide subito;
* inventare timestamp;
* inventare percorsi frame;
* marcare come certo ciò che il video non permette di capire;
* cancellare dati per semplificare una migrazione;
* costruire subito automazioni fragili per i preferiti Instagram/Facebook;
* sovra-ingegnerizzare il primo MVP.

---

# 28. Metodo di lavoro

Quando implementi una nuova parte:

1. leggi il codice esistente;
2. riutilizza ciò che è già presente;
3. fai la modifica minima coerente;
4. aggiungi test;
5. prova sul video #59;
6. mostra risultato e problemi osservati;
7. solo dopo generalizza.

Se durante il test emergono problemi reali, correggere il design in base ai dati, non in base a ipotesi astratte.

---

# 29. Obiettivo finale

Il sistema deve diventare una memoria personale degli esercizi accumulati negli anni.

L'utente deve poter salvare un video oggi e ritrovare il suo contenuto mesi o anni dopo senza riguardare decine di playlist.

Il criterio di successo è:

trovare un video
→ salvarlo
→ dimenticarsene
→ poter recuperare l'esercizio corretto quando serve
→ esportarlo velocemente in pyTrainer.
