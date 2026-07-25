# PytTrainer Android

App Android di PytTrainer: le stesse funzioni della versione desktop
(Streamlit) — scheda di allenamento in un unico file `.scheda`, ricerca
video YouTube, estrazione dei fotogrammi START/FINISH, generazione del
Google Doc A4 — più una cosa che il desktop non ha: la ricerca e la
**visione del video dentro l'app**, per catturare i due fotogrammi
scorrendo il video fotogramma per fotogramma nel punto esatto del
movimento, invece di indovinare un timestamp e riprovare.

Il file `.scheda` è **lo stesso identico** formato usato dalla versione PC
(uno zip con manifest CSV + frame + stato di ripresa): puoi aprire su
telefono una scheda creata sul PC (o dall'agente, vedi il `CLAUDE.md` alla
radice del repository) e viceversa, senza nessuna conversione.

## Come funziona dentro

Non è una riscrittura in Kotlin della logica del desktop: l'app **incorpora
un interprete Python** tramite [Chaquopy](https://chaquo.com/chaquopy/) ed
esegue gli **stessi identici file** `video_helper.py`, `scheda_file.py`,
`csv_utils.py`, `google_docs_helper.py` che vivono nella radice del
repository. Non esistono copie di questi moduli dentro `android/`: il task
Gradle `copiaModuliPython` (definito in `app/build.gradle.kts`) li copia
dalla radice a `build/generated/python` a ogni build, e Chaquopy li imbarca
da lì. Significa che non c'è mai nulla da tenere allineato manualmente tra
PC e telefono: un bugfix o una funzionalità nuova in uno di quei quattro
file vale automaticamente per entrambe le piattaforme.

L'unico file Python specifico di Android è `app/src/main/python/android_bridge.py`,
un ponte sottile verso Kotlin (vedi `PythonBridge.kt`): riceve solo
stringhe/numeri e restituisce sempre un envelope JSON `{"ok": true, "dati":
...}` / `{"ok": false, "codice": ..., "messaggio": ...}`, così nessuna
eccezione Python attraversa il confine verso Kotlin senza essere gestita.

L'unica differenza di comportamento tra le due piattaforme è **come si
estrae un fotogramma dallo stream**: sul PC `video_helper.py` chiama
`ffmpeg`, che su Android non esiste. Al suo posto, l'app registra un
backend nativo basato su `MediaMetadataRetriever` (vedi
`app/src/main/java/com/pyttrainer/android/video/EstrattoreFrameNativo.kt`),
iniettato in `video_helper` tramite `video_helper.imposta_backend_frame()`
all'avvio dell'app (`PytTrainerApplication.onCreate()`). Il resto della
logica — scelta del video, euristica dei timestamp, ripresa, generazione
del documento — è **esattamente** lo stesso codice del desktop.

## Prerequisiti

- **Android Studio** con l'SDK Android installato (`compileSdk 36`, incluse
  le Build Tools corrispondenti: Android Studio le scarica da sé al primo
  Sync se mancano).
- **JDK 17** (Android Studio ne installa uno integrato, va bene anche
  quello: non serve installarne uno a parte).
- **Un Python 3.11 installato sulla macchina che compila**, con `pip`
  funzionante. Non è l'interprete che gira sul telefono (quello lo
  impacchetta Chaquopy da sé): è l'interprete che Chaquopy usa **in fase di
  build**, sul tuo PC, per risolvere e scaricare le dipendenze Python
  dell'app (`yt-dlp`, `google-api-python-client`, Pillow, ...).

  **La versione major.minor deve corrispondere esattamente** a quella
  dichiarata in `android/gradle.properties`:

  ```properties
  pyttrainer.python.version=3.11
  ```

  Questa è l'unica riga da cambiare se un giorno si aggiorna la versione di
  Python del progetto — non toccare `app/build.gradle.kts`, la legge da lì.

  Se sulla tua macchina `python3.11` (o `python`, su Windows) non è nel
  `PATH` di sistema, oppure hai più versioni installate e non è la
  predefinita, indica a Chaquopy l'eseguibile esatto con `buildPython`, la
  leva ufficiale del plugin per questo: apri `app/build.gradle.kts`, cerca
  nel blocco `chaquopy { defaultConfig { ... } }` la riga commentata

  ```kotlin
  // buildPython("/percorso/completo/di/python3.11")
  ```

  decommentala e sostituisci il percorso con quello del tuo eseguibile (su
  Windows, tipicamente qualcosa come `C:/Python311/python.exe`, con gli
  slash normali). È l'unico punto del progetto pensato per questo valore:
  non esiste una proprietà equivalente in `gradle.properties` o
  `local.properties`, perché è tipicamente un percorso specifico di UNA
  macchina, quindi va tenuto localmente non committato (o commentato di
  nuovo prima di eventuali commit).

## Configurazione dell'accesso Google

L'accesso Google su Android usa OAuth con un client di tipo diverso da
quello della versione desktop (che usa un client "Applicazione desktop" —
vedi il `README.md` alla radice, sezione "Configurazione dell'accesso a
Google"). Se hai già un progetto Google Cloud configurato per il desktop,
puoi riusarlo: basta aggiungere un client OAuth in più, del tipo giusto.

1. Vai su [Google Cloud Console](https://console.cloud.google.com/) e apri
   il progetto che usi per PytTrainer (o creane uno nuovo).
2. Dal menu **API e servizi > Libreria**, verifica che siano abilitate
   (se non l'hai già fatto per il desktop):
   - **Google Docs API**
   - **Google Drive API**
3. Vai su **API e servizi > Schermata consenso OAuth**:
   - Tipo di utente **Esterno** (a meno di un'organizzazione Workspace).
   - Compila i campi obbligatori (nome app, email di supporto, ecc.), se
     non l'hai già fatto per il client desktop.
   - Nella sezione **Utenti di test**, assicurati che il tuo indirizzo
     email Google sia tra gli utenti autorizzati (finché l'app non è
     pubblicata, solo loro possono completare il login).
4. Vai su **API e servizi > Credenziali > Crea credenziali > ID client
   OAuth**:
   - Tipo di applicazione: **Android** (⚠️ non "Applicazione desktop": è un
     tipo di client diverso, pensato per OAuth via PKCE senza client
     secret — è quello che usa `GestoreAccessoGoogle.kt` tramite AppAuth).
   - Nome del pacchetto: `com.pyttrainer.android`.
   - Impronta del certificato di firma (SHA-1):
     ```
     59:50:55:5A:D7:D4:FB:B1:43:02:8F:D5:88:25:A4:31:89:5A:A0:86
     ```
   - Crea.

   **Perché questa SHA-1 è già nota e fissa, prima ancora che tu compili
   nulla**: il progetto include un keystore di debug **condiviso**,
   committato in `android/keystore/debug.keystore` (vedi
   `app/build.gradle.kts`, blocco `signingConfigs`). Build locali fatte da
   te e build fatte dalla CI (vedi più sotto) firmano tutte con la stessa
   chiave, quindi basta registrare **una sola** impronta SHA-1 su Google
   Cloud Console invece di una per macchina. Puoi verificare tu stesso che
   coincida con quella sopra:

   ```bash
   keytool -list -v -keystore android/keystore/debug.keystore -storepass android
   ```

   e cercare la riga `SHA1:` nell'output (alias `androiddebugkey`). Lo
   stesso identico comando gira anche nel workflow GitHub Actions, come
   promemoria automatico che la firma non è cambiata.

   Gli stessi due valori (nome pacchetto e impronta SHA-1) sono anche
   mostrati dentro l'app, in **Impostazioni**, pronti da copiare.

5. Dalla schermata delle credenziali appena create, copia il **Client ID**
   (una stringa che finisce in `.apps.googleusercontent.com`) e incollalo
   in `android/gradle.properties`:

   ```properties
   pyttrainer.oauth.clientId=IL_TUO_CLIENT_ID.apps.googleusercontent.com
   ```

   Se preferisci non modificare un file tracciato da git, puoi mettere la
   stessa riga in `android/local.properties` invece (vedi
   `android/local.properties.esempio`): quel file è locale, escluso da
   `.gitignore`, e ha la precedenza su `gradle.properties` se presente.
   Senza nessuno dei due, il progetto compila comunque (il valore di
   default è una stringa vuota), ma il pulsante "Accedi con Google"
   nell'app fallisce con un messaggio che rimanda a questa sezione, e in
   **Impostazioni** compare un avviso "Client OAuth non configurato".

## Compilare ed eseguire

1. In Android Studio, scegli **Open** e seleziona la cartella `android/`
   di questo repository (**non** la radice `PytTrainer/`: il progetto
   Gradle Android vive solo lì dentro).
2. Lascia che Android Studio faccia il **Gradle Sync** al primo avvio
   (può richiedere qualche minuto: scarica plugin, SDK e dipendenze).
3. Collega un telefono Android in **debug USB** (o via Wi-Fi, se l'hai già
   accoppiato) con il debug USB abilitato nelle opzioni sviluppatore,
   oppure avvia un emulatore con Google Play Services (serve per
   l'autenticazione Google).
4. Premi **Run** (▶). Scegli il device collegato quando richiesto.

**La prima build è lenta**, molto più lenta delle successive: Chaquopy deve
scaricare l'interprete Python da impacchettare nell'APK e fare il `pip
install` di tutte le dipendenze Python dichiarate in
`app/build.gradle.kts` (`yt-dlp`, `google-api-python-client`,
`google-auth`, Pillow, ...). Le build successive riusano la cache e sono
molto più rapide.

## Uso

Il flusso reale, dall'apertura di una scheda al documento generato:

1. **Apri o crea una scheda**: dalla schermata principale, apri un file
   `.scheda` esistente (anche uno creato sul PC) oppure comincia da una
   scheda vuota e salvala con "Salva come" quando vuoi.
2. **Aggiungi esercizi** manualmente, o importa un CSV manifest (le stesse
   colonne descritte nel `README.md` alla radice).
3. Apri un esercizio e **cerca il video** su YouTube (o incolla un URL
   direttamente).
4. **Apri il video nel player** integrato: scorri fino al punto giusto del
   movimento aiutandoti con i controlli di velocità ridotta (0.25x, 0.5x)
   e con l'avanzamento fotogramma per fotogramma, in entrambe le
   direzioni — è la parte che il desktop non offre, e il motivo per cui
   questa app esiste.
5. **Cattura START** e **cattura FINISH** nei due punti esatti. Se serve,
   ritaglia i fotogrammi catturati dalla stessa schermata di dettaglio
   dell'esercizio (con ripristino dell'originale sempre disponibile).
6. Ripeti per tutti gli esercizi, poi **genera il Google Doc**.

La generazione gira **in background** (un worker con notifica di
avanzamento: "N / M esercizi inseriti"), quindi puoi uscire dall'app
mentre procede. È **riprendibile**: se si interrompe (rete assente, app
chiusa, telefono riavviato...), rilanciando la generazione sulla stessa
scheda si riparte da dove era arrivata invece di reinserire tutto da capo
— esattamente lo stesso meccanismo di ripresa della versione desktop,
basato sullo `state.json` incluso nel bundle `.scheda`.

## Il workflow GitHub Actions

Esiste un workflow (`.github/workflows/android.yml`) che compila un APK di
debug, ma è **solo manuale**: non parte automaticamente a ogni push (la
build Android, con Chaquopy che impacchetta l'intero runtime Python, è
lenta e non ha senso lanciarla a ogni commit). Per lanciarlo:

1. Su GitHub, vai nella scheda **Actions** del repository.
2. Seleziona il workflow **Android** nella lista a sinistra.
3. Clicca **Run workflow**, scegli il branch e conferma.
4. A fine esecuzione, scarica l'artifact `pyttrainer-debug-apk` dalla
   pagina della run: è l'APK installabile.

Questo APK è firmato con lo **stesso keystore di debug condiviso**
descritto sopra (`android/keystore/debug.keystore`), quindi ha la stessa
impronta SHA-1 già registrata come client OAuth "Android" — il login
Google funziona anche installando l'APK scaricato da qui, senza dover
compilare nulla in locale.

## Risoluzione dei problemi

- **Il Gradle Sync fallisce lamentando la versione di Python / Chaquopy non
  trova l'interprete**: verifica che `python3.11` (major.minor identica a
  `pyttrainer.python.version` in `android/gradle.properties`) sia
  installato e nel `PATH`, oppure decommenta e valorizza `buildPython(...)`
  in `app/build.gradle.kts` come descritto nei Prerequisiti.
- **"Accedi con Google" fallisce subito, senza nemmeno aprire il
  browser**: il client OAuth non è configurato — vedi
  "Configurazione dell'accesso Google" sopra. La schermata Impostazioni
  mostra un avviso esplicito in questo caso.
- **Google rifiuta il login con un errore di configurazione (dopo aver
  aperto il browser)**: quasi sempre l'impronta SHA-1 registrata su Google
  Cloud Console non coincide con quella del keystore usato per compilare.
  Se stai usando una build locale (non l'APK del workflow CI) verifica di
  non aver modificato `signingConfigs` in `app/build.gradle.kts` e ricontrolla
  la SHA-1 con il comando `keytool` indicato sopra.
- **La ricerca video o l'estrazione dei fotogrammi smette di funzionare
  (video non trovati, errori strani da yt-dlp)**: YouTube cambia
  periodicamente il proprio player interno, e `yt-dlp` deve essere
  aggiornato di conseguenza. La versione usata da Android è fissata (pin)
  in `app/build.gradle.kts`, nel blocco `chaquopy { pip { install("yt-dlp==...") } }`:
  aggiornare quella riga a una release più recente di solito risolve.
  Controlla anche `requirements.txt` alla radice, che fissa la stessa
  libreria per il desktop.
- **Il player smette di riprodurre a metà sessione, con un errore di
  rete**: gli URL di stream risolti da `yt-dlp` scadono dopo qualche ora.
  Il player tenta un ri-risoluzione automatica una volta sola; se continua
  a fallire, torna indietro e riapri il video (nuova risoluzione dello
  stream).
- **Android Studio segnala dipendenze Compose/Media3 non aggiornate**: è
  atteso, non è un errore — le versioni sono fissate in
  `android/gradle/libs.versions.toml` per una build riproducibile.
  Aggiornarle è possibile ma non necessario per far funzionare l'app.

## Limiti noti

- **Uso dei termini di servizio di YouTube**: sia questa app sia la
  versione desktop leggono lo stream video tramite `yt-dlp` invece di
  passare dal player ufficiale di YouTube incorporato. Non è conforme ai
  termini di servizio di YouTube. È lo stesso comportamento che la
  versione desktop ha sempre avuto: va bene per **uso personale**, con
  l'APK installato manualmente (debug USB o "sorgenti sconosciute"), **non**
  è pensato né adatto per una pubblicazione sul Play Store.
- **Il progetto non è mai stato compilato dagli autori** in questa fase di
  sviluppo (l'ambiente in cui è stato scritto non ha l'SDK Android né
  accesso ai repository Google): è possibile che il primo Gradle Sync
  richieda qualche ritocco di versioni (AGP, Kotlin, Chaquopy o una delle
  librerie in `libs.versions.toml`) prima che tutto compili senza errori.
