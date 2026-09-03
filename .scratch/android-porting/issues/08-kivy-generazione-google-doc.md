# 08 — App Kivy: generazione Google Doc

**What to build:** Flusso di esportazione della scheda su Google Doc A4 dall'app Kivy: conteggio esercizi pronti (entrambi i frame presenti), conferma, generazione con `create_workout_document` e checkpoint dopo ogni esercizio (ripresa da `state.json` nel bundle), gestione del documento rigenerato (404 → avviso + nuovo URL), progress visibile durante la generazione, URL finale mostrato e apribile/condividibile. Funziona su PC e Android con il provider credenziali di piattaforma.

**Blocked by:** 06 — App Kivy: editor scheda

**Status:** in-progress

**Implementato nel codice (2026-09-03):** `kivy_app/export.py`
(`DocExportController`, testato senza rete/Kivy: conteggio pronti su frame
su disco, titolo da metadata o nome bundle, generazione via
`create_workout_document` con `state_path` nel work dir del bundle, ripresa
automatica da `state.json` (solo esercizi mancanti), flag
`documento_rigenerato`, persistenza dello stato nel bundle con upload Drive
tramite `editor.salva`, propagazione del SyncConflict). `progresso()` legge i
checkpoint per il poll UI. `kivy_app/export_screen.py` (UI Kivy: riepilogo
+ conferma "Avvia", worker thread, progress live per esercizio, risultato con
URL, avviso rigenerazione, azioni Apri/Condividi/Riprendi).
`kivy_app/launcher.py`: `apri_url`/`condividi_url` con browser su PC e intent
ACTION_VIEW / ACTION_SEND chooser su Android (jnius lazy).

**Fix di review applicati (2026-09-03):** ExportScreen disabilita il tasto
"< Editor" durante il worker (niente Salva concorrente con la generazione);
`genera()` passa al creator uno snapshot dei pronti (le modifiche UI non
corrompono la generazione in corso) e, se il creator fallisce, persiste
comunque l'ultimo `state.json` nel bundle prima di rialzare; `progresso()` usa
un baseline di sessione + clamp (niente >100% ne' regressioni) e il polling
tiene l'ultimo valore valido su JSON transitorio; `core.docs_helper.salva_stato`
ora e' atomico (tmp + `os.fsync` + `os.replace`), quindi il poll non legge mai
uno stato troncato; `launcher.py` ACTION_VIEW usa `Intent.setData(Uri.parse(url))`
(`setDataString` non esiste sulla classe Intent). Limite noto: un crash del
processo a meta' generazione non salva il checkpoint nel bundle (serve un
callback nel core, non in questo scope); il rilancio nello STESSO work dir
riprende comunque dai checkpoint su disco.

**Residuo:** esecuzione reale con rete su PC (login Google + Drive) e
valida su dispositivo Android (provider nativo + share sheet).

- [x] Esportazione con conteggio pronti e conferma
- [x] Progress per esercizio durante la generazione
- [x] Ripresa da stato: rilanciare dopo interruzione inserisce solo i mancanti
- [x] Documento cancellato → rigenerazione con avviso e nuovo URL
- [x] URL finale apribile e condivisibile (share sheet Android / browser PC)
- [x] Stato salvato nel bundle e sincronizzato su Drive
