# Spike 01 — PytTrainer su Android: yt-dlp + ffmpeg-kit su device reale

**Stato:** PARZIALE — rischi 1 e 2a validati, rischio 2b (estrazione frame via ffmpeg-kit)
**bloccato da un limite di binding pyjnius** (dettaglio sotto).

**Data:** 2026-09-02
**Ramo:** `android-porting` (worktree usata per la spike, non commitato)
**Device:** tablet Android (ZUI), API 33, Mali-G57 MC2, arm64-v8a

---

## Cosa è stato validato ✅

| N. | Rischio | Esito | Evidenza |
|---|---|---|---|
| 1 | yt-dlp come libreria Python sul device (ricerca) | **OK** | `SPIKE search OK n=5 title='How To Squat Correctly (NO BACK PAIN)' dur=458 url=...my0tLDaWyDU` |
| 2a | yt-dlp risolve lo stream URL del video sul device | **OK** | `SPIKE frame got stream https://rr3---sn-...googlevideo.com/videoplayback...` |
| 2b | Estrazione frame JPEG a un timestamp con ffmpeg-kit | **BLOCCATO** | `jnius` non riesce a invocare `java.lang.reflect.Method.invoke` |
| 3 | Google Sign-In nativo | **NON fatto** (decisione: "solo yt-dlp + frame nel primo giro") | — |

- L'**APK è stato buildato, installato e la UI Kivy renderizza correttamente** su hardware reale
  (OpenGL ES 3.2, window/provider sdl2, main loop attivo, nessun crash).
- **ffmpeg-kit-full 8.1.7** è **dentro l'APK**: classi Java in `classes*.dex`
  (`Lcom/arthenica/ffmpegkit/FFmpegKit;`, `ReturnCode`, ecc.) e native `.so`
  (`libffmpegkit.so`, `libavcodec.so`, `libavformat.so`, ...).
- Le classi sono **caricabili** con `PythonActivity.mActivity.getClassLoader().loadClass(...)`.

## Cosa NON ha funzionato e perché

L'unico blocco è la chiamata a `FFmpegKit.execute(String)` da Python. Il motivo è **un
limite del binding pyjnius in python-for-android**, non ffmpeg-kit:

1. **`autoclass("com.arthenica.ffmpegkit.FFmpegKit")` fallisce con `ClassNotFoundException`.**
   pyjnius usa il classloader JNI di sistema (`FindClass`), che su Android multi-dex non vede
   i dex secondari dove stanno le classi ffmpeg-kit. Aggirato caricando la classe con
   `PythonActivity.mActivity.getClassLoader().loadClass(name)` → la classe **si carica**.

2. **`java.lang.reflect.Method.invoke(...)` non è invocabile da pyjnius.**
   Il `reflect.py` di pyjnius espone `Method` ma **non dichiara il metodo `invoke`**
   (solo `getName`, `getParameterTypes`, ecc.). Ho provato:
   - aggiungere `invoke` come `JavaMultipleMethod` a runtime → `available: []`
   - patchare `reflect.py` sorgente + ricompilare il `.pyc` → ancora `available: []`
   La metaclasse `MetaJavaClass` di pyjnius costruisce la tabella dei metodi con una cache
   C all'import; patchare l'attributo di classe non la rigenera.

**Conclusione tecnica:** il problema non è ffmpeg-kit né il porting, ma **come pyjnius (nella
versione di p4a 2026.05, CPython 3.14) espone/lega i metodi di `java.lang.reflect`**. Serve
una strada diversa per invocare `FFmpegKit.execute` da Python.

## Strade possibili (da esplorare nel ticket successivo)

1. **Codice Java ponte compilato nell'app** (via source dir nella dist/build.gradle): una classe
   `FfmpegBridge` con un `static int extract(String)` che chiama `FFmpegKit` e ritorna un int
   semplice (return code). Chiamarla da Python tramite pyjnius su un tipo con un solo metodo
   primitivo — molto più semplice da legare di `Method.invoke`.
   - Nota: la classe ponte sta nell'APK main dex, quindi dev'essere in una ricetta/java source
     che p4a compila nel dex primario (stesso vincolo FindClass). Alternativa: usare
     `FFmpegKitConfig`/`FFmpegSession` via i metodi esposti direttamente, evitando reflection.
2. **Pinnare/buildare pyjnius con `invoke` dichiarato** (ricetta pyjnius custom o PR),
   oppure usare `jnius` fork che espone reflection completa.
3. **Chiamare i `.so` di ffmpeg-kit direttamente via ctypes** (cross-compilazione Python→C,
   stesso limite di `ctypes.CDLL` su Android con p4a, da validare).

## Ricetta buildozer.spec (funzionante)

```ini
[app]
title = PytTrainerSpike
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

Il rischio principale (yt-dlp su Android + ffmpeg-kit condiviso) è **confermato percorribile**.
Il pezzo 2b è un **problema di binding pyjnius**, non di ffmpeg: la strada più promettente è un
**ponte Java** (punto 1) che espone `FFmpegKit.execute` dietro un'int signle/firma primitiva,
oppure una **funzione Python→Java via ctypes** sui `.so`, oppure una **pyjnius custom che
dichiara `invoke`**. Da decidere nel ticket successivo, insieme al Sign-In nativo (rischio 3).
