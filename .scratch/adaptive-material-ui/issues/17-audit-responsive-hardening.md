# 17 — Audit responsive e hardening cross-device

**What to build:** Riesaminare l'integrazione adattiva e risolvere i problemi difficili di densità, layout, focus, tastiera, rendering o packaging che resistono al primo ciclo Luna.

**Agent:** Sol (`senior_coder`)

**Blocked by:** 16 — Integrare, compilare e correggere il primo passaggio UI

**Status:** blocked-dependency

- [ ] Nessuna schermata bypassa il modulo adattivo con euristiche locali o unità fisiche non motivate.
- [ ] Il cambio profilo, scala e orientamento simulato mantiene stato e geometria validi.
- [ ] Sono analizzati e corretti alla radice i difetti residui documentati da Luna.
- [ ] Focus, tastiera, scroll annidati e viewer immagini non causano controlli irraggiungibili.
- [ ] Tema e primitive restano un modulo profondo con interfaccia ridotta e testabile.
- [ ] Suite, harness e build APK passano dopo le correzioni.
