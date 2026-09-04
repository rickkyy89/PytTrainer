# 16 — Integrare, compilare e correggere il primo passaggio UI

**What to build:** Integrare tutte le schermate migrate, produrre build reali e correggere i difetti responsive ordinari prima dell'audit senior.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 11 — Migrare Home e Visualizzazione; 12 — Migrare Editor; 13 — Migrare Media; 14 — Migrare Modalità Allenamento; 15 — Migrare Export, dialoghi e file picker

**Status:** partial-verification

- [x] La suite completa e tutta la matrice del harness passano (`215 passed`; `python -m compileall -q kivy_app core`).
- [ ] L'APK viene compilato e installato senza regressioni di dipendenze o avvio.
- [ ] Windows viene verificato con mouse, tastiera e controlli minimi da 40dp.
- [x] Il Lenovo viene verificato realmente via USB in portrait: APK debug installato e `org.ptt.pytrainer` avviato senza crash nel logcat.
- [x] Luna corregge clipping, overlap e difetti di stile ordinari trovati nel primo passaggio.
- [ ] Ogni problema difficile residuo ha riproduzione, screenshot, log e tentativi già eseguiti per Sol.

**Environment note:** il dispositivo USB è disponibile e lo smoke test dell'APK cache è riuscito. La build dell'ultima sorgente e la matrice completa delle scale restano da eseguire quando sarà installato Buildozer; `adb` è stato usato dal percorso SDK locale.
