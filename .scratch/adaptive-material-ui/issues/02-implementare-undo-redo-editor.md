# 02 — Implementare Undo/Redo dell'editor

**What to build:** Rendere reversibili tutte le modifiche non-media dell'editor: testo, aggiunta, eliminazione, riordino, gruppo e importazioni. La cronologia deve essere utilizzabile sia dai controlli touch sia dalle scorciatoie desktop.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 01 — Progettare transazioni, cronologia e ciclo di salvataggio

**Status:** completed

- [x] Ogni campo genera una sola azione quando la modifica viene confermata uscendo dal campo.
- [x] Aggiunta, eliminazione, riordino, cambio gruppo e importazioni supportano undo e redo completi.
- [x] Una nuova modifica dopo undo elimina correttamente il ramo redo.
- [x] La cronologia conserva al massimo 20 azioni senza corrompere lo stato corrente.
- [x] L'eliminazione richiede conferma e resta annullabile dalla cronologia.
- [x] I test automatici coprono sequenze miste e ripristino esatto dei dati.
