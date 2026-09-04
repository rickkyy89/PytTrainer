# 13 — Migrare Media

**What to build:** Rendere Video/Frame una pagina Material verticale e scrollabile, con controlli adattivi sufficientemente grandi e piena integrazione con la cronologia.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 07 — Audit e hardening di Undo/Salva; 09 — Implementare fondazione Material e preferenze; 10 — Costruire harness geometrico e screenshot

**Status:** completed

- [x] URL, ricerca, timestamp ed estrazione rifluiscono senza righe orizzontali compresse.
- [x] START e FINISH si impilano in compatto e sfruttano lo spazio nei profili superiori.
- [x] Preview, scrub, slider crop e azioni rispettano tipografia e target minimi.
- [x] La tastiera non copre URL o timestamp attivi.
- [x] Undo/Redo aggiorna immediatamente campi e anteprime senza perdere file.
- [x] La pagina resta unica e lunga, senza wizard o sezioni obbligatoriamente collassate.
- [x] Harness e screenshot includono stato senza frame, frame presenti ed errore estrazione.

**Deliverable:** `kivy_app/media_layout.py`, integrazione in `kivy_app/media_screen.py` e `tests/test_media_layout.py`

**Deliverable:** `kivy_app/media_layout.py` e `tests/test_media_layout.py`
