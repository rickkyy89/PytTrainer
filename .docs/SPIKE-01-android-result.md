# Spike 01 — pyTrainer su Android: yt-dlp + ffmpeg-kit su device reale

**Stato:** SUPERATO CON WORKAROUND — rischi 1, 2a e 2b validati su device reale.
L'estrazione usa `MediaMetadataRetriever`; il percorso ffmpeg-kit resta opzionale e ha una
dipendenza Java mancante nel pacchetto mantenuto (dettaglio sotto).

**Data:** 2026-09-02
**Ramo:** `android-porting`
**Device:** tablet Android (ZUI), API 33, Mali-G57 MC2, arm64-v8a

---

## Cosa è stato validato ✅

| N. | Rischio | Esito | Evidenza |
|---|---|---|---|
| 1 | yt-dlp come libreria Python sul device (ricerca) | **OK** | `SPIKE search OK n=5 title='How To Squat Correctly (NO BACK PAIN)' dur=458 url=...my0tLDaWyDU` |
| 2a | yt-dlp risolve lo stream URL del video sul device | **OK** | `SPIKE frame got stream https://rr3---sn-...googlevideo.com/videoplayback...` |
| 2b | Estrazione frame JPEG a un timestamp | **OK con workaround nativo** | `SPIKE frame result /data/user/0/org.ptt.pttspike/files/frame_result.jpg`; JPEG estratto dallo stream YouTube (12.542 byte, magic bytes `ff d8 ff e0`) |
| 3 | Google authorization + Drive Picker nativo | **IMPLEMENTATO, test Cloud ancora necessario** | `GoogleBridge` + `ACTION_OPEN_DOCUMENT`; manca il client OAuth Android |

- L'**APK è stato buildato, installato e la UI Kivy renderizza correttamente** su hardware reale
  (OpenGL ES 3.2, window/provider sdl2, main loop attivo, nessun crash).
- **ffmpeg-kit-full 8.1.7** è **dentro l'APK**: classi Java in `classes*.dex`
  (`Lcom/arthenica/ffmpegkit/FFmpegKit;`, `ReturnCode`, ecc.) e native `.so`
  (`libffmpegkit.so`, `libavcodec.so`, `libavformat.so`, ...).
- Le classi ffmpeg-kit sono **caricabili direttamente con `autoclass(...)` sul main thread** e
  possono essere conservate e riutilizzate dal worker.

## Workaround validato per il rischio 2b

`android.media.MediaMetadataRetriever` riceve l'URL HTTPS risolto da yt-dlp, cerca il frame al
timestamp richiesto e lo comprime in JPEG nella directory privata dell'app. Il test automatico
su tablet ha prodotto un JPEG reale da 12.542 byte (magic bytes `ff d8 ff e0`):

```text
SPIKE ffmpeg classes cached on main thread
SPIKE frame got stream https://...googlevideo.com/videoplayback?...
SPIKE ffmpegkit ERR ... NoClassDefFoundError: ... smartexception ...
SPIKE frame result /data/user/0/org.ptt.pttspike/files/frame_result.jpg
```

Questo percorso usa soltanto API framework Android già disponibili e non richiede una classe
ponte, patch a pyjnius o permessi di storage: il file resta nello storage privato dell'app.

## Problema residuo di ffmpeg-kit

La precedente diagnosi sul solo limite di reflection era incompleta:

1. **`autoclass("com.arthenica.ffmpegkit.FFmpegKit")` dal worker fallisce con
   `ClassNotFoundException`.** Chiamato durante `App.build()` sul main thread, invece, funziona;
   le classi cached sono poi utilizzabili dal worker senza reflection.

2. **La chiamata diretta a `FFmpegKit.execute(String)` viene raggiunta**, ma fallisce con
   `NoClassDefFoundError: com/arthenica/smartexception/java/Exceptions`. Il POM Maven di
   `dev.ffmpegkit-maintained:ffmpeg-kit-full:8.1.7` non dichiara dipendenze transitive e il
   namespace del fork non pubblica un artefatto `smart-exception-java`.

**Conclusione tecnica:** non serve più reflection e il rischio funzionale 2b è chiuso dal
workaround framework. Ripristinare ffmpeg-kit richiederebbe reperire/compilare la dipendenza
smart-exception oppure scegliere un artefatto Android completo differente; non è necessario
per validare l'estrazione frame.

## Strade opzionali per ripristinare ffmpeg-kit

1. Aggiungere all'APK le classi `smart-exception` da una fonte verificata e compatibile.
2. Sostituire `ffmpeg-kit-full:8.1.7` con un artefatto mantenuto che includa tutte le dipendenze.
3. Rimuovere ffmpeg-kit dallo spike se `MediaMetadataRetriever` copre i formati richiesti,
   riducendo sensibilmente la dimensione dell'APK.

## Ricetta buildozer.spec (funzionante)

```ini
[app]
title = pyTrainerSpike
package.name = pttspike
package.domain = org.ptt
version = 0.1
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas
requirements = python3,kivy,yt-dlp,pyjnius
orientation = all
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.gradle_dependencies = dev.ffmpegkit-maintained:ffmpeg-kit-full:8.1.7
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 1
warn_on_root = 1
```

## Dimensioni APK e pacchetti

- **APK (debug): 57 MB** (`pttspike-0.1-arm64-v8a-debug.apk`)
- `requirements`: `python3,kivy,yt-dlp,pyjnius`
- Dipendenza Gradle: `dev.ffmpegkit-maintained:ffmpeg-kit-full:8.1.7`
  (fork mantenuto, sostituisce `com.arthenica:ffmpeg-kit` ritirato — stessa API,
  solo groupId cambiato)

## Ambiente di build (Windows + WSL)

- OS: Windows 10 + WSL2 (Ubuntu 26.04 LTS, kernel 6.18)
- Python di build: **3.11.9 via pyenv** (il venv di buildozer)
  - ⚠️ p4a/CPython per il **device** è **3.14** (hardcoded nelle recipe
    `hostpython3`/`python3` di p4a 2026.05). Non serve pyenv per il target.
- JDK 17 (openjdk), Android SDK 33 + NDK r25b, Gradle 8.11, build-tools 37.0.0
- ffmpeg di sistema in WSL: 8.0.1 (solo PC)
- ADB: usata la **platform-tools ufficiale Google v37** (l'`adb` di Ubuntu 26/apt si bloccava
  con `adb start-server` in WSL2; la v37 funziona e gira sulla LAN reale)

## Problemi risolti in build (per la documentazione)

- **`ffmpeg-kit-full` richiede minSdk ≥ 24**: alzare `android.minapi` a 24 (il target dell'app,
  Android 10+, è ben sopra).
- **Manifest merger / `--add-source .../true`**: rimuovere `android.add_src = true` (valore
  letterale) dalla spec.
- **pip 26 nel venv host p4a è rotto** (`BuildDependencyInstallError`): pin `pip<25` nel
  venv di build (patch locale a `build.py`), e aggiungere `--platform=android_24_arm64_v8a
  --implementation=cp --python-version=3.14 --only-binary=:all:` al comando di install dei
  moduli pip-core (se no pip desktop rifiuta i wheel cp314-android).
- **Connessione ADB WiFi**: `adb pair IP:porta CODICE` con porta di pairing; poi **`adb connect`
  va fatto sulla porta di connessione**, che su Android 11+ wireless debugging è DIFFERENTE da
  quella di pairing (l'IP:porta in alto nella schermata, non quella "Abbina dispositivo").
- **Install**: su questo device serve `adb shell settings put global verifier_verify_adb_installs 0`
  (e `package_verifier_enable 0`) per bypassare l'`INSTALL_FAILED_VERIFICATION_FAILURE`.

## Script di supporto (in `.scratch/android-porting/`)

- `wsl_env.sh`, `wslcmd.sh`, `run_build.sh` — avvio buildozer nell'ambiente pyenv+venv.
- `setup_spike_app.sh` — genera `main.py` + `buildozer.spec` (aggiungere qui eventuali fix).
- `patch_build.py`, `patch_pip.py` — patch temporanee a python-for-android `build.py`.
- `patch_reflect.py`, `compile_pyc.py` — tentativi di abilitare `Method.invoke` (non risolutivi).
- `check_dex.sh` — ispezione classi Java dentro l'APK.

## Raccomandazione

Il flusso necessario all'app è **confermato percorribile**: yt-dlp cerca il video e risolve lo
stream, mentre `MediaMetadataRetriever` estrae il frame JPEG sul device. Per il porting conviene
incapsulare questo backend dietro la stessa interfaccia di estrazione usata su desktop; valutare
ffmpeg-kit soltanto se test su più video evidenziano formati o seek non supportati dal retriever.

## Google Picker e prerequisito Cloud

Il percorso scelto per `drive.file` è implementato nello spike: `GoogleBridge` usa
`AuthorizationClient` per ottenere un access token con gli scope `drive.file` e `documents`, mentre
`ACTION_OPEN_DOCUMENT` apre il picker di sistema e restituisce una URI `content://` selezionata
dall'utente. Il test del consenso reale richiede un OAuth Client Android registrato con package
`org.ptt.pttspike` e SHA-1 debug:

```text
BC:F1:89:B3:03:20:ED:2D:2B:07:CA:C9:5D:B1:0C:6D:C9:B2:D2:E1
```
