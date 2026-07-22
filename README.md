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
   quella finale del movimento, ed estrai i due fotogrammi.
4. Genera il Google Doc: verrà creato un documento A4 con un modulo per
   ciascun esercizio pronto (cioè con entrambi i fotogrammi estratti).

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

Per il caricamento massivo degli esercizi, il CSV deve contenere esattamente
queste colonne (l'ordine non è rilevante):

| Nome | Spiegazione | Note | Ripetizioni | Recupero |
|------|-------------|------|-------------|----------|
| Squat con bilanciere | Posiziona il bilanciere sui trapezi... | Non far uscire le ginocchia... | 4x8 | 120 SEC |

Un file di esempio è incluso nel progetto: [`esercizi_example.csv`](esercizi_example.csv)
(scaricabile anche direttamente dall'interfaccia dell'app).

## Struttura del progetto

```
PytTrainer/
├── app.py                   # Interfaccia Streamlit (in italiano)
├── video_helper.py          # Ricerca YouTube + estrazione frame via ffmpeg
├── google_docs_helper.py    # Autenticazione e generazione del Google Doc
├── csv_utils.py             # Parsing/validazione del CSV esercizi
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
- `frames/` - cartella dove vengono salvati i fotogrammi START/FINISH
  estratti dai video.

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
