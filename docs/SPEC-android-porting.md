# SPEC — Porting Android di pyTrainer con core condiviso PC/Android

**Stato:** ready-for-agent
**Data:** 2026-09-02
**Ramo:** `android-porting`

---

## Problem Statement

pyTrainer oggi è un'app solo PC: una UI Streamlit (`app.py`) sopra quattro moduli Python
(`scheda_file`, `csv_utils`, `video_helper`, `google_docs_helper`) che generano schede
d'allenamento A4 su Google Docs partendo da file `.scheda` (zip con manifest CSV, frame
START/FINISH e stato di ripresa).

L'utente — un allenatore — vuole lavorare **anche dal telefono/tablet Android**, in palestra
e in mobilità, sugli **stessi identici file `.scheda`**: aprire una scheda fatta al PC,
modificarla sul telefono, ritrovarla aggiornata al PC. Senza duplicare la logica in due
linguaggi e senza dover mantenere due app divergenti.

Oggi questo è impossibile perché:

- La logica è mescolata con l'UI Streamlit e con l'ambiente PC (path relativi alla working
  directory, dialoghi file tkinter, binario ffmpeg di sistema, OAuth via browser locale).
- Non esiste alcuna sincronizzazione: i `.scheda` vivono solo sul disco del PC.
- Non esiste un'app Android.

## Solution

Un'unica codebase Python che gira **sia su PC sia su Android** con **Kivy**, organizzata in
un monorepo con un package `core` condiviso e privo di dipendenze UI:

- **Core condiviso**: tutta la logica di dominio esistente (bundle `.scheda`, manifest CSV,
  ricerca YouTube con yt-dlp, estrazione frame, generazione Google Doc) viene estratta in un
  package `core` che riceve le dipendenze infrastrutturali dall'esterno (dependency
  injection): directory base al posto dei path CWD-relativi, backend ffmpeg pluggabile,
  provider di credenziali Google pluggabile.
- **Sync Google Drive**: un nuovo modulo `core.drive_sync` sincronizza i `.scheda` con una
  cartella dedicata su Google Drive. Uso personale, sempre online: conflitti rilevati e
  risolti chiedendo all'utente quale versione tenere.
- **App Kivy unica**: una sola UI Kivy con cinque schermate (lista schede, editor scheda,
  scelta video e frame, generazione Google Doc, vista allenamento) che gira su PC e su
  Android (telefono + tablet, Android 10+). A regime **sostituisce Streamlit**, che viene
  dismesso.
- **Su Android il lavoro pesante resta sul device**: yt-dlp è Python puro e gira così com'è;
  ffmpeg è fornito da ffmpeg-kit dietro la stessa interfaccia del backend PC; il login Google
  usa il Google Sign-In nativo dietro la stessa interfaccia del provider PC.
- **Parità funzionale completa**: tutto ciò che l'app fa oggi su PC (ricerca video, estrazione
  frame, crop, import immagini, generazione/ripresa del Google Doc) funziona anche su Android.
- **Flusso agente evoluto**: il flusso automatico Cowork oggi documentato in CLAUDE.md non è
  un vincolo di API intoccabile; a regime sarà sostituito da una skill/plugin che genera il
  CSV/manifest per l'app. CLAUDE.md verrà aggiornato a ogni modifica delle API.

Il formato del file `.scheda` resta **esattamente quello attuale**: compatibilità totale con
i file esistenti, zero migrazione.

## User Stories

### Core e bundle `.scheda`

1. As an allenatore, I want ad aprire un file `.scheda` creato su PC anche dall'app Android, so that posso continuare a lavorare sulla stessa scheda ovunque.
2. As an allenatore, I want che il salvataggio del `.scheda` sia atomico su entrambe le piattaforme, so that un crash o un'interruzione non mi corrompa la scheda.
3. As an allenatore, I want che i frame dentro il `.scheda` mantengano gli stessi nomi canonici (`frames/<slug>_start.jpg`, `frames/<slug>_finish.jpg`) su PC e Android, so that i bundle siano intercambiabili senza rinomine.
4. As an allenatore, I want che i backup di ritaglio (`<nome>_orig.jpg`) viaggino dentro il bundle come oggi, so that posso annullare un crop anche dall'altra piattaforma.
5. As an allenatore, I want che i metadati della scheda (titolo) e lo stato di ripresa del Google Doc (`state.json`) restino dentro il bundle, so that la ripresa della generazione funzioni indipendentemente dal dispositivo.
6. As a sviluppatore, I want che il core non dipenda dalla working directory, so that lo stesso codice giri su PC, su Android e nei test senza launcher workaround.
7. As a sviluppatore, I want che il core non importi alcuna libreria UI (Streamlit, Kivy, tkinter), so that sia testabile e riusabile ovunque.

### Sincronizzazione Google Drive

8. As an allenatore, I want che tutti i miei `.scheda` vivano in una cartella dedicata su Google Drive, so that li ritrovo su tutti i dispositivi senza copie manuali.
9. As an allenatore, I want di vedere nella home dell'app la lista delle schede presenti nella cartella Drive, so that posso aprire quella che mi serve.
10. As an allenatore, I want che salvando una scheda questa venga caricata su Drive, so that sia subito disponibile sull'altro dispositivo.
11. As an allenatore, I want che aprendo una scheda l'app scarichi la versione più recente da Drive, so that non lavoro mai su una copia vecchia.
12. As an allenatore, I want che se ho modificato la stessa scheda su due dispositivi l'app mi chieda quale versione tenere, so that non perdo modifiche senza saperlo.
13. As an allenatore, I want che il rilevamento dei conflitti usi il timestamp di modifica del file su Drive confrontato con la copia locale, so that il caso "last-write-wins silenzioso" non avvenga mai senza il mio consenso.
14. As an allenatore, I want di poter creare una nuova scheda dall'app e trovarla nella cartella Drive, so that il flusso di creazione è identico su PC e Android.
15. As an allenatore, I want di poter eliminare una scheda dall'app con conferma, so that la cartella Drive resta pulita.
16. As an allenatore, I want che l'app mi avvisi chiaramente se sono offline, so that so che le modifiche non si stanno sincronizzando (l'app è sempre-online per design).

### Autenticazione Google

17. As an allenatore, I want che su Android il login Google usi il flusso nativo con l'account del telefono, so that non devo copiare file di token dal PC.
18. As an allenatore, I want che su PC il login continui a funzionare come oggi (browser + token salvato), so that non devo riconfigurare nulla.
19. As an allenatore, I want che le credenziali OAuth siano configurate una sola volta per piattaforma, so that poi tutto è automatico.
20. As a sviluppatore, I want che il core riceva le credenziali da un provider iniettato, so that il flusso OAuth di piattaforma è intercambiabile senza toccare la logica di generazione documenti.

### Video e frame

21. As an allenatore, I want cercare video YouTube per un esercizio dall'app Android, so that posso aggiungere esercizi nuovi anche dal telefono.
22. As an allenatore, I want che la ricerca mostri titolo, durata e anteprima dei risultati come oggi, so that scelgo il video giusto al primo colpo.
23. As an allenatore, I want impostare i timestamp START/FINISH ed estrarre i frame sul telefono, so that non devo passare dal PC per completare una scheda.
24. As an allenatore, I want che l'euristica 10%/50% proponga timestamp iniziali sensati, so that il lavoro manuale è minimo.
25. As an allenatore, I want ritagliare i frame (crop per lati, in percentuale) anche su Android, so that le immagini nella scheda sono pulite.
26. As an allenatore, I want usare una foto dalla galleria del telefono al posto di un frame estratto, so that posso usare immagini mie per esercizi senza video buoni.
27. As an allenatore, I want che `scegli_ed_estrai` rispetti le scelte già presenti nel manifest (VideoURL, timestamp, frame esistenti) esattamente come oggi, so that rilanciare l'estrazione è idempotente su entrambe le piattaforme.
28. As a sviluppatore, I want che il backend ffmpeg sia iniettato (binario di sistema su PC, ffmpeg-kit su Android), so that la logica di estrazione è scritta una volta sola.

### Generazione Google Doc

29. As an allenatore, I want generare il Google Doc A4 della scheda anche dall'app Android, so that posso consegnare/stampare la scheda senza accendere il PC.
30. As an allenatore, I want che la generazione salvi un checkpoint dopo ogni esercizio inserito e riprenda da dove si è interrotta, so that una connessione ballerina in palestra non mi fa ricominciare da zero.
31. As an allenatore, I want che se il Google Doc puntato dallo stato è stato cancellato, l'app lo rigeneri da zero avvisandomi, so that non resto con una scheda orfana.
32. As an allenatore, I want correggere video/timestamp di un singolo esercizio e aggiornare solo quello nel documento, so that non rigenero tutta la scheda per una correzione.
33. As an allenatore, I want vedere l'URL del documento generato e poterlo aprire/condividere dall'app, so that lo mando subito all'atleta.

### Editor scheda

34. As an allenatore, I want creare, rinominare, riordinare ed eliminare esercizi nella scheda dall'app, so that gestisco tutta la scheda dal telefono.
35. As an allenatore, I want organizzare gli esercizi in gruppi/sezioni (es. Attivazione), so that la scheda stampata ha la struttura che voglio.
36. As an allenatore, I want importare esercizi da un CSV o da un'altra scheda, so that riuso schede esistenti senza riscrivere tutto.
37. As an allenatore, I want un indicatore di modifiche non salvate, so that so sempre se devo salvare/sincronizzare.
38. As an allenatore, I want che gli slug duplicati tra esercizi omonimi siano segnalati, so that i frame non si sovrascrivono nel bundle.

### Vista allenamento

39. As an allenatore/atleta, I want una vista "in palestra" con i frame grandi e le informazioni essenziali (ripetizioni, recupero, note), so that la scheda è leggibile a colpo d'occhio mentre mi alleno.
40. As an allenatore/atleta, I want poter spuntare gli esercizi completati durante l'allenamento, so that so a che punto sono.
41. As an allenatore/atleta, I want un timer di recupero avviabile dalla vista allenamento, so that rispetto i tempi senza cambiare app.

### Esperienza multi-dispositivo

42. As an allenatore, I want che l'app si adatti a telefono e tablet, so that sul tablet sfrutto lo schermo grande (es. lista + dettaglio affiancati).
43. As an allenatore, I want che l'app giri su Android 10+, so that copre il mio telefono e praticamente tutti i dispositivi recenti.
44. As an allenatore, I want installare l'app via APK firmato senza Play Store, so that la distribuzione personale è semplice.

### Migrazione e qualità

45. As a sviluppatore, I want che il flusso legacy a CSV sciolto sia eliminato nel refactor, so that resta una sola modalità supportata: il bundle `.scheda`.
46. As a sviluppatore, I want una suite pytest sul core (bundle, CSV, sync, stato ripresa), so that il refactor non rompe il comportamento esistente.
47. As a sviluppatore, I want che CLAUDE.md sia aggiornato a ogni cambio di API del core, so that gli agenti Cowork continuano a operare correttamente.
48. As an allenatore, I want che i miei `.scheda` esistenti si aprano senza alcuna conversione, so that non perdo il lavoro fatto finora.

## Implementation Decisions

### Architettura del monorepo

- Un unico repository con tre aree: package `core` (logica di dominio, zero UI), package/app
  Kivy (UI condivisa PC+Android), suite `tests` (pytest sul core). L'app Streamlit resta
  funzionante sopra il core fino alla dismissione.
- Il core non importa alcuna libreria UI. La dipendenza UI → core è a senso unico.

### Astrazioni iniettate nel core (le tre seam infrastrutturali)

1. **Base directory / storage**: nessun path CWD-relativo nel core. Credenziali, token, cache
   di lavoro (`.work`) e directory frame sono sempre ricavati da una directory base esplicita
   passata dal chiamante. Non serve alcun launcher che cambi directory per compensare path
   relativi delle credenziali.
2. **Backend ffmpeg**: interfaccia unica "estrai un frame JPEG a timestamp T da uno stream
   URL con questi header HTTP". Implementazione PC: binario `ffmpeg` via subprocess
   (comportamento attuale, incluso fallback anti-403 con download temporaneo su urllib).
   Implementazione Android: ffmpeg-kit. Il resto di `video_helper` (yt-dlp, euristica
   timestamp, filtro pertinenza, crop con PIL) è invariato e condiviso.
3. **Provider credenziali Google**: interfaccia unica "dammi credentials valide `.drive` +
   `.documents`". Implementazione PC: service account se presente, altrimenti OAuth browser
   con token cache su file (comportamento attuale, incluso flusso manuale headless).
   Implementazione Android: Google Sign-In nativo con token gestito dal sistema.

### Moduli del core

- `core.csv_utils` — invariato nelle API: `slugify`, `slugs_unici`, `trova_duplicati_slug`,
  `parse_esercizi_csv`, `scrivi_esercizi_csv`, `esercizi_csv_bytes`. Mapping dict↔CSV
  invariato (11 colonne, 5 obbligatorie + 6 opzionali).
- `core.scheda_file` — API invariate: `carica_scheda`, `carica_scheda_da_file_like`,
  `salva_scheda`, `scheda_bytes`, `cartella_lavoro_per_bundle`, `cartella_frames`,
  `percorso_stato`, `titolo_scheda`. Formato bundle invariato (`scheda.csv` + `frames/` +
  `metadata.json` + `state.json`, guardie zip-slip, scrittura atomica tmp+replace, backup
  `_orig.jpg`). Aggiunta solo la dipendenza dalla base directory iniettata per la cache.
- `core.video_helper` — API invariate: `search_youtube`, `get_stream_info`,
  `get_stream_url`, `extract_frame`, `extract_start_finish_frames`,
  `filtra_risultati_pertinenti`, `get_video_info`, `scegli_ed_estrai`, `box_ritaglio`,
  `crop_frame`, `importa_frame_da_immagine`. yt-dlp resta usato come libreria con
  `player_client: android`. La chiamata ffmpeg passa dal backend iniettato; il default
  `"frames"` come output_dir resta ma relativo alla base directory iniettata.
- `core.docs_helper` (oggi `google_docs_helper`) — API invariate: `get_credentials`,
  `get_credentials_manual_flow`, `upload_image_to_drive`, `delete_drive_file`,
  `carica_stato`, `salva_stato`, `create_workout_document`, `update_exercise_media`.
  Gli helper interni oggi privati usati dagli script legacy NON vengono promossi pubblici:
  gli script legacy sono eliminati. Struttura dello `state.json` invariata
  (`doc_id`, `titolo`, `url`, `esercizi[]` con `nome/slug/named_range_id/gruppo`).
- `core.drive_sync` — NUOVO. Responsabilità:
  - lista dei `.scheda` nella cartella Drive dedicata (cartella configurabile; oggi l'ID è
    hardcoded in app.py, diventa configurazione);
  - download di un `.scheda` nella cache locale con tracciamento del timestamp di modifica
    remoto;
  - upload di un `.scheda` nuovo o modificato;
  - rilevamento conflitto: la copia locale è stata modificata E anche quella remota è più
    recente dell'ultimo sync → il core espone il conflitto all'UI, che chiede all'utente
    quale versione tenere (o di creare una copia). Il core non decide mai da solo;
  - creazione ed eliminazione di schede nella cartella;
  - richiede rete: niente coda offline (decisione: sempre online).

### App Kivy

- Cinque schermate: **Lista schede** (home, da Drive), **Editor scheda** (lista esercizi
  completa di gruppi, riordino, import CSV/scheda, indicatore modifiche non salvate),
  **Scelta video e frame** (ricerca YouTube, anteprime, timestamp, estrazione, crop,
  import da galleria), **Generazione Google Doc** (con ripresa da stato e gestione doc
  rigenerato), **Vista allenamento** (frame grandi, spunta esercizi, timer recupero).
- Layout responsive telefono/tablet; target Android 10+; packaging con buildozer, APK
  firmato per installazione personale (niente Play Store).
- File picker: su Android si usa il picker di sistema via plyer (niente tkinter, che resta
  solo nella vecchia app Streamlit fino a dismissione).
- File picker immagini su Android: galleria di sistema via plyer.

### Script legacy e asset PC-only eliminati

- Eliminato il flusso a CSV sciolto e cartella di stato separata; esiste solo il bundle
  `.scheda`.
- `app.py` (Streamlit) resta finché l'app Kivy non raggiunge parità funzionale, poi viene
  eliminato. Fino ad allora va fatto girare sopra il nuovo `core` (import aggiornati).

### Flusso agente Cowork

- Le API del core possono cambiare durante il refactor; a ogni cambio CLAUDE.md va
  aggiornato (è già una regola del repo).
- A regime: una skill/plugin dedicata genera il CSV/manifest iniziale da dare in pasto
  all'app, sostituendo il flusso automatico end-to-end attuale. Esiste già una skill
  `genera-csv-scheda` in `.opencode/skills` come punto di partenza.

### Decisioni di sync (riassunto)

- Cartella Drive dedicata come unica fonte di verità condivisa.
- Sempre online: niente editing offline, niente coda di sync.
- Conflitto = modifica locale + modifica remota dall'ultimo sync → dialogo all'utente
  (tieni locale / tieni remota / duplica). Mai last-write-wins silenzioso.

## Testing Decisions

- **Cos'è un buon test qui**: testa solo comportamento esterno osservabile delle API
  pubbliche del core, mai dettagli interni. I test devono girare su PC senza rete e senza
  credenziali Google reali (mock/fake ai confini: backend ffmpeg, provider credenziali,
  client Drive/Docs).
- **Seam di test**: il boundary del package `core`. È la seam più alta stabile tra PC e
  Android; le tre astrazioni iniettate (storage, ffmpeg, credenziali) sono i punti dove i
  test attaccano i fake. Nessun test sulla UI Kivy (verificata a mano).
- **Moduli testati**:
  - `core.scheda_file`: round-trip carica/salva, atomicità (tmp+replace), guardie zip-slip,
    gestione backup `_orig.jpg`, metadata/state opzionali, slug collisioni nel bundle.
    (Prior art: `tests/test_scheda_file.py` esiste già e va portato sul nuovo package.)
  - `core.csv_utils`: parsing valido/invalido, timestamp opzionali, round-trip bytes.
  - `core.drive_sync`: logica di rilevamento conflitto e decisioni upload/download contro un
    fake client Drive (nessuna chiamata reale).
  - `core.docs_helper`: macchina a stati di ripresa (`state.json`: checkpoint per esercizio,
    rigenerazione su 404) con servizi Docs/Drive mockati. (Prior art: `tests/test_smoke.py`
    copre già questi scenari e va portato sul nuovo package.)
  - `core.video_helper`: filtro pertinenza, euristica timestamp, crop/box_ritaglio su
    immagini finte; estrazione frame con backend ffmpeg fake.
- **Prior art**: esistono già `tests/test_scheda_file.py` (~293 righe) e
  `tests/test_smoke.py` (~1113 righe) con `pytest` in `requirements-dev.txt`. I test
  esistenti vanno migrati sul package `core` come prima prova che il refactor preserva il
  comportamento.

## Out of Scope

- Distribuzione su Play Store (APK personale firmato).
- Supporto iOS.
- Modalità offline / coda di sincronizzazione (decisione esplicita: sempre online).
- Merge automatico dei conflitti di sync (sempre dialogo all'utente).
- Multi-utente, account, condivisione di schede tra utenti diversi.
- Cambiamenti al formato del `.scheda` e allo `state.json` (compatibilità totale).
- Riscrittura dell'UI Streamlit (resta com'è fino a dismissione).
- Skill/plugin agente definitiva (viene dopo, come evoluzione del flusso Cowork).
- Internazionalizzazione: l'app resta in italiano.

## Further Notes

- **Rischi tecnici principali** (da mitigare con spike precoci):
  1. yt-dlp su Android via buildozer: è Python puro ma va validato subito.
  2. ffmpeg-kit come backend Android: dimensioni APK e API bridge da validare.
  3. Google Sign-In nativo + scope `drive.file`/`documents` da Android: flusso OAuth da
     validare con un'app scheletro.
  Si raccomanda una spike tecnica (app Kivy minima che fa: ricerca yt-dlp + estrazione un
  frame + login Google) prima o all'inizio del lavoro sulla UI.
- **Decisione CSV**: `core.csv_utils` usa il modulo standard `csv`, non `pandas`. Il parser
  conserva le API e il mapping delle 11 colonne, inclusi input testuali e binari e il
  round-trip; i test del core ne verificano il comportamento. Questo rimuove la dipendenza
  Python piu pesante dal porting Android. Le dipendenze attuali sono: streamlit, yt-dlp,
  pillow, google-api-python-client, google-auth-httplib2, google-auth-oauthlib.
- La cartella Drive oggi hardcoded in `app.py`
  (`1UthYZdR1GiVADYNUWBN1cX3z790FEkXq`) diventa configurazione dell'app.
- Branch di lavoro: `android-porting` (creato da `claude/pc-refactor-schede`).
