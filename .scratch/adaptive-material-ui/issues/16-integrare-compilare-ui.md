# 16 — Integrare, compilare e correggere il primo passaggio UI

**What to build:** Integrare tutte le schermate migrate, produrre build reali e correggere i difetti responsive ordinari prima dell'audit senior.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 11 — Migrare Home e Visualizzazione; 12 — Migrare Editor; 13 — Migrare Media; 14 — Migrare Modalità Allenamento; 15 — Migrare Export, dialoghi e file picker

**Status:** partial-verification

- [x] La suite completa e tutta la matrice del harness passano (`215 passed`; `python -m compileall -q kivy_app core`).
- [ ] L'APK viene compilato e installato senza regressioni di dipendenze o avvio.
- [ ] Windows viene verificato con mouse, tastiera e controlli minimi da 40dp.
- [ ] Il Lenovo viene verificato realmente in portrait con target da 48dp e tutte le scale.
- [x] Luna corregge clipping, overlap e difetti di stile ordinari trovati nel primo passaggio.
- [ ] Ogni problema difficile residuo ha riproduzione, screenshot, log e tentativi già eseguiti per Sol.

**Environment note:** APK/build/installazione Android e verifica fisica Lenovo restano da eseguire su una macchina con toolchain Android e dispositivo disponibili.
