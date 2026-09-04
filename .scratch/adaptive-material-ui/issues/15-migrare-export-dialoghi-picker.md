# 15 — Migrare Export, dialoghi e file picker

**What to build:** Uniformare tutte le superfici secondarie al nuovo sistema Material, eliminando popup e barre con misure fisiche o testo non avvolto.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 09 — Implementare fondazione Material e preferenze; 10 — Costruire harness geometrico e screenshot

**Status:** completed

- [x] Export e avanzamento rifluiscono e restano scrollabili in compatto.
- [x] Conflitti, conferme, scelta salvataggio e impostazioni usano dialoghi con larghezza massima e corpo scrollabile.
- [x] File picker e pulsanti rispettano target touch e pointer previsti.
- [x] Testi lunghi, errori e scala 130% non oltrepassano i dialoghi.
- [x] Focus, tastiera e azione predefinita funzionano su Android e Windows.
- [x] Colori, icone, bordi e stati sono coerenti con le schermate principali.

**Deliverable:** `kivy_app/secondary_layout.py` e `tests/test_secondary_layout.py`
