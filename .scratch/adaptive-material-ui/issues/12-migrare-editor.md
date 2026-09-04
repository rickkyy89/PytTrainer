# 12 — Migrare Editor

**What to build:** Trasformare l'editor in un'esperienza Material adattiva che mantiene sempre leggibili campi e azioni e integra i controlli sicuri di Undo/Redo/Salva.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 07 — Audit e hardening di Undo/Salva; 09 — Implementare fondazione Material e preferenze; 10 — Costruire harness geometrico e screenshot

**Status:** completed

- [x] In compatto gli esercizi formano una fisarmonica con un solo elemento aperto e riepiloghi leggibili.
- [x] Le etichette stanno sopra i campi in compatto e possono affiancarsi nei profili più larghi.
- [x] Video/Frame resta visibile; riordino, gruppi ed elimina sono nel menu overflow.
- [x] Aggiungi resta visibile; importazioni ed export sono raccolti nel menu azioni.
- [x] Una barra inferiore fissa espone Undo, Redo e Salva con stato delle modifiche.
- [x] Il campo attivo viene portato sopra la tastiera e la barra resta raggiungibile.
- [x] Nessun profilo o livello di scala presenta label tra textbox, testo illeggibile o controlli troppo piccoli.

**Deliverable:** `kivy_app/editor_layout.py` e `tests/test_editor_layout.py`
