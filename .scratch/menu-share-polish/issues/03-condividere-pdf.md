# 03 - Esportare e condividere il PDF

**What to build:** Dopo la generazione del Google Doc, Condividi esporta il documento in PDF e propone le normali destinazioni Android, incluse mail e salvataggio locale; sul PC rende disponibile il PDF nel sistema.

**Blocked by:** None - can start immediately.

**Status:** completed

- [x] Il documento viene esportato via Drive API come `application/pdf` in un file temporaneo valido.
- [x] Android apre uno share sheet con il PDF come allegato e concede accesso in lettura alle app destinatarie.
- [x] Il PC apre il PDF tramite il gestore di sistema, permettendo il normale salvataggio locale.
- [x] Errori di export o condivisione vengono mostrati all'utente e l'operazione non blocca la UI.
- [x] Il comportamento e coperto da test headless senza chiamate di rete reali.
