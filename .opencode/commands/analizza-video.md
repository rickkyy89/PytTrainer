---
description: Prepara e analizza visivamente un singolo video della pytrainer-library
---

Orchestra l'analisi del video database #$1 della pytrainer-library fino alla produzione dei JSON, senza importarlo nel database e senza generare CSV.

1. Prepara soltanto il video richiesto nella pytrainer-library e i suoi artefatti visivi con il codice deterministico disponibile.
2. Delega la prima analisi al subagente locale `scrutatore`, fornendo ID video, percorsi degli artefatti e formato JSON atteso. Scrutatore usa modello principale e fallback della sua configurazione corrente, impostabili con `/sub_models scrutatore`. Deve salvare `analysis/work/$1/ai_result_<modello>.json` nella library, usando un suffisso sicuro per il filesystem e indicando nel JSON il modello effettivamente usato. Se il subagente non e' disponibile nella sessione, chiedi di riavviare OpenCode per caricare la configurazione della repo.
3. Leggi il JSON e validalo con il codice Python, senza importarlo.
4. Se uno o piu esercizi hanno confidence minore di `0.75`, riesamina gli stessi artefatti visivi e salva un secondo file `ai_result_<modello>_review.json`.
5. Indica chiaramente se la revisione migliora la confidence o se i dubbi persistono.
6. Riporta numero di esercizi, incertezze, modello effettivo e percorsi dei JSON.

Non eseguire `analysis_io.py import`, non modificare SQLite e non creare CSV. Se i dubbi persistono dopo il secondo parere, chiedi all'utente di rivedere soltanto i tratti dubbi.
