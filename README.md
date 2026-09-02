# Workout Sheet Automator

App web locale in Streamlit per creare schede di allenamento in formato A4
direttamente su Google Docs. Permette di inserire gli esercizi (manualmente o
tramite CSV), cercare video dimostrativi su YouTube, estrarre automaticamente
i fotogrammi della posizione di partenza (START) e di fine movimento (FINISH)
con ffmpeg, e generare un documento Google Docs A4 verticale con un modulo
per esercizio (immagini a sinistra, dettagli testuali a destra).

## Descrizione

Il flusso di lavoro tipico è:

1. Inserisci gli esercizi della scheda (a mano o caricando un CSV).
2. Per ogni esercizio, cerca un video YouTube che mostri l'esecuzione
   corretta (oppure incolla direttamente un URL).
3. Scegli i secondi (timestamp) in cui si vede la posizione di partenza e
   quella finale del movimento, ed estrai i due fotogrammi. In alternativa,
   con **🖼️ Scegli immagine START / FINISH** puoi usare due immagini tue
   (foto, screenshot, disegni) al posto dei fotogrammi estratti: vengono
   convertite in JPEG e trattate come qualsiasi altro fotogramma, ritaglio
   compreso. Un esercizio può quindi essere completato anche senza video.
4. Genera il Google Doc: verrà creato un documento A4 con un modulo per
   ciascun esercizio pronto (cioè con entrambi i fotogrammi estratti).

In qualsiasi momento puoi salvare o scaricare la scheda come bundle `.scheda`
(manifest CSV, fotogrammi e stato di ripresa nello stesso archivio) per
riprenderla più tardi. Il CSV resta disponibile solo come formato di import
degli esercizi. Puoi inoltre ritagliare (crop) i fotogrammi START/FINISH
direttamente dall'anteprima, con possibilità di ripristinare l'originale.

Per riordinare la lista, ogni esercizio ha un campo **Posizione** con il
pulsante **↕️ Sposta**: scegli il numero a cui vuoi portarlo e tutti gli altri
scorrono di conseguenza. La casella di selezione a sinistra di ogni esercizio
abilita invece le azioni di gruppo nella barra in cima alla lista, con cui
puoi spostare in blocco (mantenendo l'ordine relativo) o eliminare più
esercizi in una volta sola.

L'app funziona interamente in locale: i video non vengono mai scaricati per
intero, viene solo letto lo stream necessario a estrarre i due fotogrammi.

## Prerequisiti

- **Python 3.10 o superiore**
- **ffmpeg** installato e disponibile nel PATH di sistema (serve per
  estrarre i fotogrammi dai video). Comandi di installazione:

  ```bash
  # Debian/Ubuntu
  sudo apt update && sudo apt install ffmpeg

  # macOS (Homebrew)
  brew install ffmpeg

  # Windows (winget)
  winget install ffmpeg
  ```

  Puoi verificare l'installazione con `ffmpeg -version`. L'app stessa mostra
  un avviso se non trova ffmpeg nel PATH.

## Setup dell'ambiente

```bash
# Crea e attiva un ambiente virtuale
python3 -m venv venv
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate         # Windows

# Installa le dipendenze
pip install -r requirements.txt
```

## Configurazione dell'accesso a Google (Docs + Drive)

L'app supporta due modalità di autenticazione: **OAuth utente** (consigliata
per l'uso personale, il documento appartiene al tuo account) oppure
**Service Account** (nessuna interazione utente, ma il documento appartiene
all'account di servizio).

### Opzione A - OAuth utente (consigliata)

1. Vai su [Google Cloud Console](https://console.cloud.google.com/) e crea
   un nuovo progetto (oppure selezionane uno esistente).
2. Dal menu **API e servizi > Libreria**, cerca e abilita:
   - **Google Docs API**
   - **Google Drive API**
3. Vai su **API e servizi > Schermata consenso OAuth**:
   - Scegli tipo di utente **Esterno** (a meno di avere un'organizzazione
     Google Workspace).
   - Compila i campi obbligatori (nome app, email di supporto, ecc.).
   - Nella sezione **Utenti di test**, aggiungi il tuo indirizzo email
     Google (finché l'app non è pubblicata, solo gli utenti di test
     autorizzati possono autenticarsi).
4. Vai su **API e servizi > Credenziali > Crea credenziali > ID client
   OAuth**:
   - Tipo di applicazione: **Applicazione desktop**.
   - Dai un nome a piacere e crea.
5. Scarica il file JSON delle credenziali appena create e rinominalo
   `credentials.json`, posizionandolo nella cartella principale del
   progetto (`/home/user/PytTrainer/credentials.json`).
6. Al primo utilizzo della generazione documento, l'app aprirà una finestra
   del browser per completare l'autorizzazione; al termine verrà creato
   automaticamente un file `token.json` che verrà riutilizzato (e rinnovato
   automaticamente) nelle esecuzioni successive.

### Opzione B - Service Account

1. Segui i passi 1-2 sopra per abilitare le API.
2. Vai su **API e servizi > Credenziali > Crea credenziali > Account di
   servizio**, crealo e genera una chiave in formato JSON.
3. Rinomina il file scaricato `service_account.json` e posizionalo nella
   cartella principale del progetto.
4. **Nota importante**: con questa modalità i documenti e i file caricati su
   Drive apparterranno all'account di servizio, non al tuo account
   personale. Se vuoi vederli nel tuo Drive dovrai condividerli
   manualmente, oppure impostare una condivisione automatica lato Drive.

Se è presente `service_account.json`, l'app userà sempre questa modalità
(ha priorità sull'OAuth utente).

## Avvio dell'app

```bash
streamlit run app.py
```

L'app si aprirà nel browser all'indirizzo indicato in console (di norma
`http://localhost:8501`).

## Formato del file CSV

Per il caricamento massivo degli esercizi, il CSV deve contenere almeno
queste 5 colonne obbligatorie (l'ordine non è rilevante):

| Nome | Spiegazione | Note | Ripetizioni | Recupero |
|------|-------------|------|-------------|----------|
| Squat con bilanciere | Posiziona il bilanciere sui trapezi... | Non far uscire le ginocchia... | 4x8 | 120 SEC |

Un file di esempio è incluso nel progetto: [`esercizi_example.csv`](esercizi_example.csv)
(scaricabile anche direttamente dall'interfaccia dell'app).

## Manifest CSV nel bundle

Oltre alle 5 colonne obbligatorie, il manifest `scheda.csv` contenuto nel
bundle `.scheda` supporta 6 colonne opzionali. Se assenti (o vuote), si usa la
ricerca automatica del video e l'euristica sui timestamp. Un CSV esteso può
anche essere importato nell'interfaccia Streamlit per precompilare URL video,
timestamp e anteprime dei frame.

| Colonna | Obbligatoria | Descrizione |
|---|---|---|
| `Gruppo` | no | Nome della sezione/sottogruppo (es. `Attivazione`). Se assente, tutti gli esercizi finiscono in un gruppo implicito senza intestazione. |
| `VideoURL` | no | URL YouTube scelto/forzato per l'esercizio. Se presente, salta la ricerca automatica e usa direttamente questo video. |
| `TimestampStart` | no | Secondo del frame START. Se assente, si applica l'euristica del 10% della durata del video. |
| `TimestampFinish` | no | Secondo del frame FINISH. Se assente, euristica del 50% della durata. |
| `FrameStartPath` / `FrameFinishPath` | no | Percorso dei frame già estratti in una run precedente. Se presenti e i file esistono ancora, la ri-estrazione viene saltata. |

Al salvataggio il manifest, i frame e lo stato vengono ricompattati nel bundle
`.scheda`. Riaprirlo e rilanciare la generazione dà lo stesso risultato
(idempotenza); modificare `VideoURL` o i timestamp nell'esercizio permette di
correggere un solo esercizio senza rifare tutto da capo.

## Ripresa e stato

`create_workout_document(..., state_path=...)` salva `state.json` nella
cartella di lavoro del bundle, con il `doc_id` del documento e l'elenco degli
esercizi già inseriti (nome, slug, id del named range che li àncora nel
documento, gruppo). `salva_scheda(..., state_path=...)` lo include nel bundle.
Se l'esecuzione si interrompe a metà, riaprire lo stesso `.scheda` riusa il
documento esistente e aggiunge solo gli esercizi mancanti. Per ricominciare da
zero, elimina `state.json` dalla cartella di lavoro e salva nuovamente il
bundle senza `state_path`.

Se il documento a cui punta lo stato è stato cancellato da Drive, non serve
fare nulla a mano: alla generazione successiva la scheda viene rigenerata
automaticamente in un documento nuovo con tutti gli esercizi (l'app lo
segnala, e l'URL del documento cambia). Restano invece un errore i casi
diversi da "documento inesistente" — per esempio un problema di permessi o di
rete — per non creare un doppione del documento.

Lo stesso file di stato serve anche per `update_exercise_media()`, che
sostituisce solo i due frame (START/FINISH) di un esercizio già presente nel
documento, individuandolo tramite il named range salvato nello stato.

## Autenticazione in ambienti senza browser

`get_credentials()` presuppone un browser locale disponibile (usa
`flow.run_local_server()`). In un contesto di esecuzione remota/headless
(agente, CI, sandbox) questo non è possibile: usa invece
`google_docs_helper.get_credentials_manual_flow()`, che separa il flusso in
due chiamate:

1. `get_credentials_manual_flow()` (senza argomenti): solleva
   `GoogleAuthError` il cui messaggio contiene l'URL di autorizzazione da
   aprire in un browser qualsiasi (anche su un altro dispositivo).
2. Dopo aver autorizzato l'accesso, si viene reindirizzati a un URL del tipo
   `http://localhost/?code=...` (va bene copiarlo anche se la pagina non si
   carica). Richiamare `get_credentials_manual_flow(auth_code=<code o URL
   copiato>)` completa il login e salva `token.json`, esattamente come dopo
   un login interattivo riuscito con `get_credentials()`.

## Struttura del progetto

```
PytTrainer/
├── app.py                   # Interfaccia Streamlit (in italiano)
├── core/                    # Logica condivisa, senza dipendenze UI
├── video_helper.py          # Wrapper compatibile di core.video_helper
├── google_docs_helper.py    # Wrapper compatibile di core.docs_helper
├── csv_utils.py             # Wrapper compatibile di core.csv_utils
├── requirements.txt         # Dipendenze Python
├── esercizi_example.csv     # CSV di esempio
├── README.md
├── .gitignore
└── tests/
    └── test_smoke.py        # Test automatici (senza rete/credenziali reali)
```

File generati/usati a runtime (esclusi da git, vedi `.gitignore`):

- `credentials.json` / `service_account.json` - credenziali Google (da
  configurare come descritto sopra).
- `token.json` - token OAuth generato automaticamente dopo il primo login.
- `<nome>.scheda.work/` - cache estraibile e rigenerabile del bundle, con
  frame e `state.json`.

## Esecuzione dei test

```bash
pip install pytest
pytest
```

I test non richiedono rete né credenziali Google reali: usano mock per le
API Google e, se ffmpeg è disponibile, generano un piccolo video sintetico
locale per testare l'estrazione dei fotogrammi.

## Risoluzione dei problemi comuni

- **"File 'credentials.json' non trovato"**: segui la sezione
  "Configurazione dell'accesso a Google" sopra. In alternativa usa un
  Service Account (`service_account.json`).
- **Token scaduto / errore di autenticazione dopo un po' di tempo**: elimina
  il file `token.json` e riavvia l'app; verrà richiesta una nuova
  autorizzazione tramite browser.
- **"ffmpeg non risulta installato"**: installa ffmpeg come indicato nei
  prerequisiti e assicurati che il comando `ffmpeg -version` funzioni dal
  terminale in cui lanci Streamlit.
- **Estrazione frame che fallisce / video non disponibile**: alcuni video
  YouTube limitano l'accesso diretto allo stream (età, restrizioni
  geografiche, video privati/rimossi). Prova a scegliere un altro video tra
  i risultati di ricerca, oppure incolla manualmente l'URL di un video
  alternativo.
- **Timestamp FINISH non accettato**: il secondo di FINISH deve essere
  strettamente maggiore del secondo di START.
- **Le immagini non compaiono nel Google Doc generato**: verifica che
  l'account usato abbia i permessi per creare file su Google Drive (scope
  `drive.file`) e che la rete non blocchi l'accesso a `drive.google.com`.
