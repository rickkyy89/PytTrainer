# 09 — Implementare fondazione Material e preferenze

**What to build:** Realizzare il modulo adattivo, il tema dark professionale e le primitive condivise che sostituiranno misure e widget incoerenti nelle schermate.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 08 — Progettare il modulo adattivo Material

**Status:** completed

- [x] Le schermate possono ottenere profilo, orientamento, scala e token da una sola interfaccia.
- [x] Il tema usa superfici dark, accento verde acqua, contrasto leggibile, bordi sobri e nessuna animazione.
- [x] Font e icone bundled rendono in modo coerente su Android e Windows.
- [x] Sono disponibili primitive Material per testo auto-height, pulsanti, campi, card, toolbar, menu e dialoghi.
- [x] Impostazioni offre Auto, 100%, 115% e 130% e conserva la scelta localmente.
- [x] Il cambio scala o viewport aggiorna la UI senza riavvio e senza leggere densità direttamente nelle schermate.
- [x] Test unitari coprono classificazione profili, token e persistenza preferenze.

**Deliverable:** `kivy_app/material.py` e `tests/test_material.py`
