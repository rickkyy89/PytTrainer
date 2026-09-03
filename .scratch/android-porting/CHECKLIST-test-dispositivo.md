# CHECKLIST — Test su dispositivo Android (ticket 05, 06, 07, 08, 09, 10)

> Da eseguire sul telefono/tablet dopo aver installato l'APK debug.
> Segna ogni voce con ✅/❌/⚠️ e una nota. Le voci con 🔗 sono i blocchi
> noti documentati nei ticket (OAuth nativo + prova dispositivo).

## 0. Prerequisiti (PC)

- [ ] APK ricostruito DOPO i fix desktop del 03/09 (commit `bf68f94`):
      controllare che `bin/pyTrainer-0.1-arm64-v8a-debug.apk` abbia data/ora
      successiva alla rebuild (`git log -1 --format=%cd bf68f94`).
      Log rebuild: `.scratch/android-porting/rebuild_desktop_fixes.log`
      (deve finire con `[INFO]: Build #... ended` senza errori).
- [ ] Sanity APK da WSL:
      `wsl -d Ubuntu -- bash /mnt/c/PyTrainer/PC/PytTrainer/.scratch/android-porting/check_apk.sh`
      atteso: package `org.ptt.pytrainer` (tutto minuscolo), `LEAKS: none`.
- [ ] 🔗 Google Cloud: client OAuth Android con package ESATTO
      `org.ptt.pytrainer` (NON `org.ptt.pyTrainer`) e SHA-1 debug:
      `BC:F1:89:B3:03:20:ED:2D:2B:07:CA:C9:5D:B1:0C:6D:C9:B2:D2:E1`
      (vedi ticket 05). Se il client non è ancora configurato, il login
      nativo fallirà già al passo 1: configurarlo prima.
- [ ] Dispositivo: Android 10+, USB debugging attivo (o copia file via
      cavo/Drive), account Google di servizio pyTrainer presente sul telefono.

## 1. Installazione e avvio

- [ ] `adb install -r bin\pyTrainer-0.1-arm64-v8a-debug.apk`
      (adb: `C:\Users\rickk\AppData\Local\Android\Sdk\platform-tools\adb.exe`)
- [ ] Avvio app → compare la richiesta di accesso Google (Google Sign-In
      nativo) → scegliere l'account → autenticazione completata
      senza copiare token da PC. 🔗 (blocco ticket 05)
- [ ] Home carica da sola / con "Aggiorna": lista delle `.scheda` della
      cartella Drive `1UthYZdR1GiVADYNUWBN1cX3z790FEkXq` con nome + data.
- [ ] "Cartelle": mostra la cartella corrente; aggiungi/seleziona un'altra
      cartella Drive → la lista si aggiorna (opzionale, se hai una 2a cartella).

## 2. Scheda: lettura e scrittura

- [ ] Apri una scheda → visualizzazione sola lettura SCORREVELE, card con
      titolo/ripetizioni/recupero, intestazioni di gruppo, immagini contenute
      (fix desktop oggi: verificare che ci siano anche sul telefono).
- [ ] "Modifica" → editor: liste scorrevoli, campi visibili senza
      sovrapposizioni in PORTRAIT e in LANDSCAPE (riga campi 1-4 colonne al
      variare della larghezza).
- [ ] Modifica un esercizio, "Vai a…" → sposta l'esercizio alla posizione X.
- [ ] "Salva solo locale" → badge "da sincronizzare"; "Salva su Drive" →
      badge pulito; controlla su PC (refresh Drive) che il file sia aggiornato.
- [ ] Crea scheda nuova da "Nuova scheda" → la trovi nel Drive (PC) e la
      rielencchi con "Aggiorna".
- [ ] Importa da scheda: "Inserisci in una posizione" → gli esercizi finiscono
      nel punto scelto.
- [ ] Elimina una scheda di prova con conferma → sparisce da Drive.

## 3. Video & Frame (ticket 07)

- [ ] Cerca su un esercizio senza video → risultati con anteprima YouTube,
      titolo e durata, lista scorrevole.
- [ ] Seleziona un video → timestamp euristica 10%/50% compilati.
- [ ] **Slider START/FINISH**: la pista è abilitata solo con video+durata;
      trascinando cambia l'etichetta "Tempo: X s" e arriva l'anteprima del
      frame estratto dallo stream (conferma: l'immagine mostrata cambia).
- [ ] "Estrai frame" → frame reali nel bundle; "Salva su Drive" → rivedi la
      scheda da PC: i frame ci sono.
- [ ] Crop (cursori sinistra/alto/destra/basso + Applica/Ripristina) funziona
      e non sovrappone controlli; "Immagine…" → galleria di sistema, la foto
      scelta diventa il frame.
- [ ] Play → apre YouTube/app video sul secondo START, poi torna all'app.

## 4. Allenamento (ticket 09)

- [ ] "Allenati" dalla visualizzazione → frame grandi, info essenziali,
      lista scorrevole; spunta esercizi → contatore progressi.
- [ ] "▶ Recupero N" → countdown nel ticker in basso, "Stop" lo azzera;
      a scadenza: notifica di fine recupero (permesso notifiche concessa).
- [ ] "▶ Video" sulla card → apre il player esterno; "‹ Scheda" → torna alla
      visualizzazione (non alla lista).

## 5. Google Doc (ticket 08)

- [ ] Da editor → "Genera Google Doc": riepilogo pronti/totali, "Avvia" →
      progress live; a fine generazione URL + "Apri documento"/"Condividi"
      (share sheet Android).
- [ ] Ripresa: avvia la generazione e chiudi l'app a metà; riapri, stesso
      percorso → riprende inserendo SOLO i mancanti (stesso doc).
- [ ] Il doc e lo stato sono nel bundle: da PC, "Aggiorna" + apertura scheda
      → stato recuperato.

## 6. Conflitti di sync (ticket 10)

Prepara: scheda S modificata e salvata da telefono SENZA premere
"Salva su Drive"… più semplice:
- [ ] Modifica S su PC (o qui) e salvala; poi modifica S sull'altro
      dispositivo senza caricare; all'apertura/salvataggio successivo deve
      comparire il DIALOGO CONFLITTO con i due timestamp e 3 scelte.
- [ ] "Tieni locale" → su Drive c'è la versione locale (verifica da PC).
- [ ] (nuovo conflitto) "Tieni remota" → locale sovrascritta, nessun danno.
- [ ] (nuovo conflitto) "Duplica" → su Drive appare "... (2).scheda" e
      l'originale resta la versione remota; tornare alla lista aggiornata.
- [ ] Mai sovrascrizioni silenziose.

## 7. Offline / rete ballerina

- [ ] Modalità aereo + "Aggiorna" → messaggio chiaro "Drive non
      disponibile", l'app non crasha; ritorno online → refresh ok.

## Registro risultati

| # | Voce | Esito | Note |
|---|------|-------|------|
|   |      |       |      |

## Se qualcosa fallisce

- Crash all'avvio: `adb logcat -s python:V SDLActivity:V | tail -50`
- Login: verificare package/SHA-1 del client OAuth (passo 0.3);
  `adb shell dumpsys package org.ptt.pytrainer | grep versionName`
- Allegare screenshot del problema + il log sopra nel ticket relativo.
