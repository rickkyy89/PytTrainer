# 05 — App Kivy: lista schede da Drive

**What to build:** Prima schermata dell'app Kivy (funzionante su PC e Android): home che elenca le schede presenti nella cartella Drive dedicata con nome e data modifica; apertura di una scheda (download + `carica_scheda`) in sola lettura con elenco esercizi e frame; creazione di una nuova scheda vuota (upload su Drive); eliminazione con conferma. Avviso chiaro se offline. Login Google all'avvio con il provider di piattaforma (OAuth browser su PC, Google Sign-In su Android). La navigazione verso l'editor esiste ma l'editing arriva nel ticket successivo.

**Blocked by:** 01 — Spike Android; 04 — `core.drive_sync`

**Status:** in-progress

**Implementato nel codice:** home Kivy PC con controller testabile, cartelle
Drive locali persistenti (iniziale `1UthYZdR1GiVADYNUWBN1cX3z790FEkXq`),
lista/refresh, download e lettura sola, creazione/upload, conferma
eliminazione e stato Drive non disponibile. La composizione PC usa
`LocalCredentialsProvider` e la build del client Drive in modo lazy/iniettabile.

**Blocco residuo:** rimangono l'installazione/verifica su dispositivo e
l'OAuth di produzione. ATTENZIONE: l'APK debug ha `applicationId`
**`org.ptt.pytrainer`** (tutto minuscolo, p4a normalizza il nome): in Google
Cloud il client OAuth Android va registrato con package esatto
`org.ptt.pytrainer` (NON `org.ptt.pyTrainer`), SHA-1 debug:

```text
BC:F1:89:B3:03:20:ED:2D:2B:07:CA:C9:5D:B1:0C:6D:C9:B2:D2:E1
```

**Build debug completata (2026-09-03):** `buildozer -v android debug` ha
prodotto `bin/pyTrainer-0.1-arm64-v8a-debug.apk` (41 MB, arm64-v8a, API 24-33,
verify assente di file sensibili dalla dist). Fix applicati per arrivarci:
`main.py` root come entry point verso `kivy_app.main.run()`; esclusione da
`source.exclude_dirs`/`exclude_patterns` di `.buildozer`, `bin`, `drive-cache`,
cartelle `.work`, `token.json`, `credentials.json`, `*.scheda`; patch pip
cross-install per la cache p4a di produzione
(`.scratch/android-porting/patch_build_prod.py`, log
`.scratch/android-porting/prod_build2.log`).

- [x] Home con lista schede da Drive (nome + data modifica), aggiornabile
- [x] Apertura scheda in sola lettura: esercizi e frame visibili
- [x] Creazione nuova scheda vuota sincronizzata su Drive
- [x] Eliminazione scheda con conferma
- [x] Avviso offline visibile
- [x] Login Google funzionante su PC (token refresh + flusso loopback verificati)
- [ ] Login Google funzionante su Android (client OAuth `org.ptt.pytrainer` dichiarato configurato; da verificare su dispositivo)
- [x] Build debug APK interna generata (41 MB, arm64-v8a)
- [ ] App installata e verificata su dispositivo Android reale

**Rebuild APK 16:07 (2026-09-03):** dopo i fix desktop del pomeriggio
(commit `bf68f94`, codice condiviso con Android) l'APK delle 11:53 era
obsoleto; `buildozer -v android debug` rigenerato in WSL (log
`.scratch/android-porting/rebuild_desktop_fixes.log`), `check_apk.sh`
conferma package `org.ptt.pytrainer` e `LEAKS: none` (41 MB, 16:07).

**Prossimo passo dispositivo:** seguire
`.scratch/android-porting/CHECKLIST-test-dispositivo.md` (prerequisiti
OAuth/SHA-1, installazione, verifica di tutte le schermate 05-10 sul
telefono, registro risultati).
