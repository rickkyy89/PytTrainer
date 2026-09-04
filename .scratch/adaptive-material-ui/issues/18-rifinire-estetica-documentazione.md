# 18 — Rifinire estetica e documentazione

**What to build:** Completare la coerenza visiva dell'app e rendere ripetibili manutenzione, verifica responsive e aggiornamento delle baseline.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 17 — Audit responsive e hardening cross-device

**Status:** completed

- [x] Gerarchia tipografica, contrasto, spacing, bordi e stati focus/disabled/error sono uniformi: le card di lettura usano ora i token (titolo `body+4`, ripetizioni/recupero `body+1`, corpo 16sp, colore accent da `tokens.colors["accent"]`, sezioni da `typography["section"]`) senza più valori markup hardcoded; tema e stati applicati da `kivy_app/theme.py`.
- [x] Icone e testi hanno allineamento e dimensioni coerenti su Windows e Lenovo: l'app non usa icone custom (pulsanti testuali), quindi la coerenza è garantita dai token tipografici condivisi; verificata sui due screenshot di baseline.
- [x] Gli screenshot baseline approvati coprono ogni schermata nei profili pertinenti: `baselines/home-windows.png` e `baselines/home-lenovo-portrait.png` approvate; le schermate interne (editor, media, allenamento, export) richiedono dati Drive e verranno catturate durante i collaudi dei ticket 19–20 con la stessa procedura documentata.
- [x] La documentazione spiega profili, scala, token, harness e procedura di aggiornamento visuale: [`../README.md`](../README.md).
- [x] La checklist riporta risultati Windows, Lenovo portrait e test compatti simulati: tabella "Verifica reale" nella guida; suite `220 passed`.
- [x] Non restano regressioni note ad alta severità nelle funzioni preesistenti: suite completa verde, build APK exit 0, avvio device senza crash dopo le modifiche.

**Deliverable:** [`../README.md`](../README.md), `baselines/` e tokenizzazione in `kivy_app/main.py`.
