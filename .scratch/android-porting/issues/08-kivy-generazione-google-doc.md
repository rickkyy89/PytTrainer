# 08 — App Kivy: generazione Google Doc

**What to build:** Flusso di esportazione della scheda su Google Doc A4 dall'app Kivy: conteggio esercizi pronti (entrambi i frame presenti), conferma, generazione con `create_workout_document` e checkpoint dopo ogni esercizio (ripresa da `state.json` nel bundle), gestione del documento rigenerato (404 → avviso + nuovo URL), progress visibile durante la generazione, URL finale mostrato e apribile/condividibile. Funziona su PC e Android con il provider credenziali di piattaforma.

**Blocked by:** 06 — App Kivy: editor scheda

**Status:** blocked-dependency

**Blocco attuale:** richiede l'editor Kivy del ticket 06, a sua volta bloccato
dalla home del ticket 05 e dalla validazione OAuth Android del ticket 01.

- [ ] Esportazione con conteggio pronti e conferma
- [ ] Progress per esercizio durante la generazione
- [ ] Ripresa da stato: rilanciare dopo interruzione inserisce solo i mancanti
- [ ] Documento cancellato → rigenerazione con avviso e nuovo URL
- [ ] URL finale apribile e condivisibile (share sheet Android / browser PC)
- [ ] Stato salvato nel bundle e sincronizzato su Drive
