# 11 — Migrare Home e Visualizzazione

**What to build:** Rendere lista schede e visualizzazione leggibili e gradevoli su tutti i profili, sfruttando lo spazio aggiuntivo senza rimpicciolire testo e controlli.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 09 — Implementare fondazione Material e preferenze; 10 — Costruire harness geometrico e screenshot

**Status:** completed

- [x] La home compatta usa card apribili al tap con azioni secondarie in menu e conferma eliminazione.
- [x] Il profilo espanso usa master-detail tra lista e visualizzazione.
- [x] La visualizzazione usa card con corpo 16sp a scala 100%, gerarchia chiara e testo sempre completo.
- [x] START e FINISH sono verticali in compatto e affiancati quando lo spazio lo consente.
- [x] Il tap su un frame apre fullscreen con zoom e passaggio START/FINISH tramite swipe.
- [x] Su desktop il contenuto è centrato con larghezza massima leggibile.
- [x] Harness e screenshot coprono nomi, note e spiegazioni lunghe.

**Deliverable:** `kivy_app/home_layout.py`, integrazione in `kivy_app/main.py` e `tests/test_home_layout.py`
