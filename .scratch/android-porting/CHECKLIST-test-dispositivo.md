# CHECKLIST DISPOSITIVO — Test Android pyTrainer

> Quando rientri: segui dall'alto. Ogni passo ha COMANDO, AZIONE e
> **Risultato atteso**; segna ✅/❌/️ e una nota. Fermati e segna ⛔ se un
> blocco ti impedisce di proseguire i passi successivi.
>
> APK da installare: `bin/pyTrainer-0.1-arm64-v8a-debug.apk` (deve avere
> data/ora **16:07 o successiva** del 03/09 — include i fix desktop
> `bf68f94`).

---

## FASE 0 — Prerequisiti PC (5 min, senza telefono)

- [ ] **0.1 APK fresco**
  ```powershell
  Get-Item C:\PyTrainer\PC\PytTrainer\bin\pyTrainer-0.1-arm64-v8a-debug.apk
  ```
  Atteso: LastWriteTime ≥ 03/09 16:07, ~41 MB. Se più vecchio: rebuild
  (`wsl -d Ubuntu` → `/mnt/c/PyTrainer/PC/PytTrainer` →
  `.scratch/android-porting/wslcmd.sh buildozer -v android debug`, log in
  `.scratch/android-porting/rebuild_desktop_fixes.log`).

- [ ] **0.2 Sanity APK**
  ```powershell
  wsl -d Ubuntu -- bash /mnt/c/PyTrainer/PC/PytTrainer/.scratch/android-porting/check_apk.sh
  ```
  Atteso: `package: name='org.ptt.pytrainer'` e `LEAKS: none`.

- [ ] **0.3 Client OAuth Android su Google Cloud** (⛔ se mancante, la Fase 2
  non può funzionare)
  Console → API e servizi → Credenziali → deve esistere un client **Android**
  con:
  - package ESATTO: `org.ptt.pytrainer` (tutto minuscolo!)
  - SHA-1 debug: `BC:F1:89:B3:03:20:ED:2D:2B:07:CA:C9:5D:B1:0C:6D:C9:B2:D2:E1`
  - OAuth consent screen: account di servizio tra gli utenti test (o app
    verificata)
  Segna qui lo stato: ☐ già presente ☐ creato ora ☐ mancante ⛔

---

## FASE 1 — Installazione

- [ ] **1.1 Collega il tablet** (USB con debug, o installa copiando l'APK)
  ```powershell
  $adb = "C:\Users\rickk\AppData\Local\Android\Sdk\platform-tools\adb.exe"
  & $adb devices          # atteso: il dispositivo con 'device'
  ```

- [ ] **1.2 Installa**
  ```powershell
  & $adb install -r C:\PyTrainer\PC\PytTrainer\bin\pyTrainer-0.1-arm64-v8a-debug.apk
  ```
  Atteso: `Success`. Se firma diversa da installazioni precedenti:
  `& $adb uninstall org.ptt.pytrainer` e riprova.

- [ ] **1.3 Permesso notifiche**: avvia l'app e concedi i permessi richiesti
  (notifiche serviranno nel test 7.3).

## FASE 2 — Login Google nativo 🔗 (il blocco principale)

- [ ] **2.1** Apri pyTrainer → attesa splash → prompt **Google Sign-In
  nativo** (pupzza account del tablet, non browser).
  Atteso: scegli account → spinner → home con "0/N schede" o lista.
  Esito: ☐ ok ☐ gira a vuoto ☐ errore (screenshot + `adb logcat -s python:V`)

- [ ] **2.2** "Aggiorna" → lista delle `.scheda` della cartella Drive
  (`1UthYZdR1GiVADYNUWBN1cX3z790FEkXq`) con nome + data, uguale a quella del
  PC.
- [ ] **2.3** Kill forzato dell'app e riavvio: login **già attivo** (token
  sopravvive), lista si ricarica in pochi secondi.
- [ ] **2.4** "Cartelle": mostra la cartella attuale; aggiungi un altro ID e
  selezionala → lista cambia; torna a quella normale.
- [ ] **2.5 Offline**: modalità aereo → "Aggiorna" → messaggio "Drive non
  disponibile. Verifica la connessione", niente crash; online → refresh ok.

## FASE 3 — Scheda: lettura / creazione / cancellazione (ticket 05)

- [ ] **3.1** Apri una scheda (es. "Anca e Core") → **sola lettura**:
  barra fissa `< Lista | Modifica | Allenati` in alto; la lista SCORRE col
  dito; card con titolo/ripetizioni/recupero, intestazioni gruppo verdi,
  frame START/FINISH contenute nella larghezza (niente foto tagliate).
- [ ] **3.2** `< Lista` → torna alla lista schede.
- [ ] **3.3** "Nuova scheda" → nome `ZTEST tablet` → ok: compare in lista;
  verifica da PC che `ZTEST tablet.scheda` è su Drive (o da "Aggiorna").
- [ ] **3.4** "Elimina" su `ZTEST tablet` → conferma → sparisce (e da Drive).

## FASE 4 — Editor (ticket 06)

- [ ] **4.1** Scheda → "Modifica": header `< Indietro | status | Salva solo
  locale | Salva su Drive`; la lista esercizi scorre; i campi Nome/Gruppo/
  Ripetizioni/Recupero sono in riga su tablet, su più righe in portrait
  stretto (ruota il tablet e verifica il ri-flusso senza sovrapposizioni).
- [ ] **4.2** Modifica un campo e clicca fuori → status "« modifiche non
  salvate".
- [ ] **4.3** "Salva solo locale" → bundle scritto, status "Scheda salvata
  in locale (Drive non aggiornato)"; "Salva su Drive" → status "Salvato su
  Drive" (verifica da PC).
- [ ] **4.4** "Aggiungi esercizio" (in fondo), "Su"/"Giù", ed **"Vai a…"** →
  sposta un esercizio alla posizione 1 e a metà lista → riedita e salva.
- [ ] **4.5** "Gruppi" sul secondo esercizio → popup con gruppi esistenti →
  scegli → intestazione di gruppo aggiornata dopo il salvataggio (in sola
  lettura).
- [ ] **4.6** Due esercizi con lo stesso nome → status rosso "ATTENZIONE slug
  duplicati".
- [ ] **4.7** "Importa CSV" → file picker DI SISTEMA Android: seleziona un
  .csv nella memoria → popup 3 scelte → "Inserisci in una posizione" (es. 2)
  → gli esercizi importati partono da lì.
- [ ] **4.8** "Importa da scheda" → scegli un'altra scheda → Aggiungi in
  fondo; `< Indietro` dall'editor → torna alla **visualizzazione**, non alla
  lista.
- [ ] **4.9** Elimina un esercizio, salva, verifica da PC.

## FASE 5 — Video & frame (ticket 07)

- [ ] **5.1** Scheda → Modifica → "Video&Frame" su un esercizio SENZA video:
  "Cerca" → risultati con anteprima, titolo, durata; seleziona uno → URL
  applicato, timestamp euristica.
- [ ] **5.2** **Slider START e FINISH**: piste abilitate con
  "Tempo: X s (video: m:ss)"; trascina → l'immagine sotto cambia (frame
  estratto dallo stream, senza aprire YouTube). Se il drag muove la pagina
  invece della pista: segna ❌ con log.
- [ ] **5.3** Muovi la pista con un tocco secco a metà: campo "Start s"/
  "Finish s" si aggiorna.
- [ ] **5.4** "Estrai frame" → "frame: OK"; `< Editor` → "Salva su Drive" →
  da PC ricarica la scheda e verifica i nuovi frame nel bundle.
- [ ] **5.5** Crop: cursori sinistra/alto/destra/basso → anteprima live,
  "Applica"; "Ripristina" torna indietro; "Immagine…" → galleria SAF, scegli
  una foto → diventa il frame.
- [ ] **5.6** "Play" (riga video) → apre YouTube/app player sul secondo
  START; torna all'app.
- [ ] **5.7** "Estrai frame" di nuovo: non deve ri-estrarre (log "frame già
  presenti"), se non forzi cambiando ts (in questo caso il pulsante estrae
  sempre: nota il comportamento).

## FASE 6 — Google Doc (ticket 08)

- [ ] **6.1** Da editor (scheda con ≥3 esercizi pronti): "Genera Google Doc"
  → riepilogo "pronti N/M" → "Avvia" → progress live a percentuale.
- [ ] **6.2** A circa metà generazione **chiudi l'app** (kill). Riapri, stesso
  percorso, "Avvia" di nuovo → riprende: progress riparte dai mancanti e il
  documento è LO STESSO (url invariato).
- [ ] **6.3** "Apri documento" → browser; "Condividi" → share sheet Android.
- [ ] **6.4** Verifica su Drive: il `.scheda` contiene lo stato (da PC:
  ricrearlo con lo zip viewer o riesportare senza rigenerazione).

## FASE 7 — Allenamento (ticket 09)

- [ ] **7.1** Scheda → "Allenati": card con frame grandi, checkbox,
  timer; "‹ Scheda" torna alla visualizzazione.
- [ ] **7.2** Spunta 2 esercizi → contatore "x/N completati"; "Azzera".
- [ ] **7.3** "▶ Recupero N" → countdown nel ticker; metti il tablet in home
  e attendi la scadenza → **notifica di fine recupero**; "Stop" interrompe.
- [ ] **7.4** "▶ Video" → player esterno sul secondo START (se l'esercizio
  ha il video).

## FASE 8 — Conflitti sync (ticket 10) — servono PC + tablet

Prepara una scheda `ZTEST conflitti.scheda` (o usa una copia) creata dal PC.

- [ ] **8.1 "locale"**: tablet apre la scheda (la scarica). PC: modifica
  (cambia ripetizioni), salva. Tablet: modifica UN ALTRO campo, "Salva su
  Drive" → **dialogo con i due timestamp e 3 scelte** (verifica layout:
  niente testo tagliato, pulsanti premibili, niente doppio tap). Scegli
  **Tieni locale** → da PC: Drive mostra la versione del tablet.
- [ ] **8.2 "remota"**: ripeti il doppio scenario; scegli **Tieni remota** →
  tablet torna alla LISTA con messaggio, riaprendo la scheda vedi la
  versione PC, modifiche tablet scartate, nessun nuovo dialogo (chiuso).
- [ ] **8.3 "duplica"**: ripeti; scegli **Duplica** → su Drive compare
  `ZTEST conflitti (2).scheda` con la versione tablet, l'originale resta la
  versione PC; messaggio sulla home, conflitto risolto.
- [ ] **8.4** Conflitto aperto da home (prima di entrare): dopo 8.1 senza
  uscire dal tablet, modifica ancora in locale via PC, poi tocca la scheda
  nella lista → il dialogo compare ALL'APERTURA.
- [ ] **8.5** Mai sovrascrizioni silenziose: in tutti i passi, nessuna
  modifica è andata persa senza dialogo (nota qualsiasi caso).
- Cleanup: elimina `ZTEST conflitti*` da entrambi.

## FASE 9 — Tablet / orientamenti

- [ ] **9.1** Landscape: home, editor, sola lettura — layout si riadatta
  (griglia campi più colonne, nessuna sovrapposizione).
- [ ] **9.2** Rotazione DURANTE: editor aperto con modifiche non salvate →
  ruota → l'app NON deve crashare né perdere l'editor (Kivy di default non
  ricrea: nota se viene chiesto di ruotare).
- [ ] **9.3** Dimensione caratteri/pulsanti usabile col dito (min 44dp
  effettivi): segnala qualsiasi pulsante "difficile".

---

## RACCOLTA LOG (se qualcosa fallisce)

```powershell
$adb = "C:\Users\rickk\AppData\Local\Android\Sdk\platform-tools\adb.exe"
& $adb logcat -d -s python:V SDLActivity:V > C:\PyTrainer\pyt_logcat.txt
# riproduci il bug, poi riesporta e allega/pyt_logcat.txt nel ticket
```

Screenshot del problema (tablet): `Vol+Power` (o
`& $adb exec-out screencap -p > shot.png`).

## REGISTRO RISULTATI

| # | Fase | Esito | Nota |
|---|------|-------|------|
| 0.1 | APK fresco | | |
| 0.3 | OAuth client | | |
| 2.1 | Login nativo | | |
| 2.2 | Lista Drive | | |
| 2.5 | Offline | | |
| 3.1 | Sola lettura | | |
| 4.1 | Editor responsivo | | |
| 4.3 | Salva locale/Drive | | |
| 4.7 | Picker+import pos. | | |
| 5.2 | Scrub slider | | |
| 5.5 | Crop+galleria | | |
| 5.6 | Play | | |
| 6.1 | Genera doc | | |
| 6.2 | Ripresa | | |
| 7.3 | Timer+notifica | | |
| 8.1 | Conflitto locale | | |
| 8.2 | Conflitto remota | | |
| 8.3 | Conflitto duplica | | |
| 9.1 | Landscape | | |

Stato ticket alla fine: 05 ☐ 06 ☐ 07 ☐ 08 ☐ 09 ☐ 10 ☐ (da chiudere nel
rispettivo file di `.scratch/android-porting/issues/` + commit).
