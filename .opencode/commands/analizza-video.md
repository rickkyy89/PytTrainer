---
description: Prepara e analizza visivamente un singolo video della pytrainer-library
agent: build
---

Orchestra l'analisi del video database #$1 della pytrainer-library fino alla produzione dei JSON, senza importarlo nel database e senza generare CSV.

1. Delega sempre la prima analisi a `scrutatore`, che usa Luna con fallback Flash.
2. Scrutatore prepara soltanto il video richiesto e salva `analysis/work/$1/ai_result_<modello>.json`.
3. Leggi il JSON e validalo con il codice Python, senza importarlo.
4. Se uno o piu esercizi hanno confidence minore di `0.75`, riesamina gli stessi artefatti visivi con il modello effettivo dell'agente build e salva un secondo file `ai_result_<modello-build>.json`.
5. Indica chiaramente se il secondo parere migliora la confidence o se i dubbi persistono.
6. Riporta numero di esercizi, incertezze, modello effettivo e percorsi dei JSON.

Non eseguire `analysis_io.py import`, non modificare SQLite e non creare CSV. Se i dubbi persistono dopo il secondo parere, chiedi all'utente di rivedere soltanto i tratti dubbi.
