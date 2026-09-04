# 08 — Progettare il modulo adattivo Material

**What to build:** Definire una seam unica e testabile che nasconda densità, viewport, scala utente, modalità touch/pointer e token visivi, così le schermate chiedono un profilo senza duplicare euristiche.

**Agent:** Sol (`senior_coder`)

**Blocked by:** 07 — Audit e hardening di Undo/Salva

**Status:** completed

- [x] Sono definiti i profili compatto 400–599dp, medio 600–959dp ed espanso da 960dp.
- [x] La scala Auto segue il sistema; 100%, 115% e 130% la sostituiscono e persistono solo sul dispositivo.
- [x] Il contratto distingue controlli touch da almeno 48dp e controlli Windows pointer da almeno 40dp.
- [x] Tipografia, spacing, altezze, larghezze massime, colori, bordi, font e icone hanno token centralizzati.
- [x] Il design specifica reflow, keyboard avoidance, contenuto max-width e comportamento alla rotazione.
- [x] Viewport e metriche sono iniettabili nel test harness senza dipendere dal provider Window reale.
- [x] Il passaggio a Luna non lascia decisioni architetturali aperte.

**Deliverable:** [`../08-contratto-modulo-adattivo-material.md`](../08-contratto-modulo-adattivo-material.md)
