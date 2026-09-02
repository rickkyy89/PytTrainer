# 03 — Eliminare script legacy e dipendenze PC-only

**What to build:** Rimossi dal repo gli script del flusso legacy a CSV sciolto (`build_doc.py`, `build_doc_step.py`, `process_one.py`, `run_flow.py`) e il launcher `avvia_app.bat` (reso inutile dall'eliminazione dei path CWD-relativi). Rimosso l'uso di tkinter dai percorsi condivisi (resta solo nella vecchia app Streamlit fino a dismissione). Valutata e decisa la sostituzione di pandas con il modulo `csv` standard in `core.csv_utils` (a parità di comportamento, coperta dai test) per alleggerire il porting Android; la decisione è documentata. CLAUDE.md aggiornato: la modalità "CSV sciolto + cartella state/" non esiste più, esiste solo il bundle `.scheda`.

**Blocked by:** 02 — Estrarre package `core`

**Status:** done

- [x] `build_doc.py`, `build_doc_step.py`, `process_one.py`, `run_flow.py`, `avvia_app.bat` eliminati
- [x] Nessun riferimento residuo agli script legacy nel codice e nella documentazione
- [x] Decisione pandas-vs-csv presa e documentata; test di `csv_utils` verdi a parità di comportamento
- [x] Test suite verde dopo le rimozioni
- [x] CLAUDE.md aggiornato (solo flusso bundle `.scheda`)
