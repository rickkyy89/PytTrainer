# 16 — Integrare, compilare e correggere il primo passaggio UI

**What to build:** Integrare tutte le schermate migrate, produrre build reali e correggere i difetti responsive ordinari prima dell'audit senior.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 11 — Migrare Home e Visualizzazione; 12 — Migrare Editor; 13 — Migrare Media; 14 — Migrare Modalità Allenamento; 15 — Migrare Export, dialoghi e file picker

**Status:** ready-for-review

- [x] La suite completa e tutta la matrice del harness passano (`215 passed`; `python -m compileall -q kivy_app core`).
- [x] L'APK viene compilato (Buildozer in WSL, target android arm64-v8a) e installato sul Lenovo senza regressioni di dipendenze; l'avvio iniziale è crashato per `ImportError: profile_for_window` (funzione mai definida in `kivy_app/material.py`), corretta e riverificata: home Material renderizzata in portrait senza crash.
- [ ] Windows viene verificato con mouse, tastiera e controlli minimi da 40dp.
- [x] Il Lenovo viene verificato realmente via USB in portrait: APK debug installato e `org.ptt.pytrainer` avviato senza crash nel logcat.
- [x] Luna corregge clipping, overlap e difetti di stile ordinari trovati nel primo passaggio.
- [ ] Ogni problema difficile residuo ha riproduzione, screenshot, log e tentativi già eseguiti per Sol.

**Environment note:** build realizzata in WSL Ubuntu (Buildozer 1.6.0 in `~/.venvs/buildozer`, distribuzione p4a riutilizzata da `.buildozer`). Al primo avvio l'APK crashava per l'ImportError sopra: logcat catturato, fix applicato in `kivy_app/material.py`, APK ricostruito, installato e verificato in foreground con screenshot della home. Resta la verifica Windows desktop e la matrice scale su dispositivo.
