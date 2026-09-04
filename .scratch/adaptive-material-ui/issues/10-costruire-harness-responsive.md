# 10 — Costruire harness geometrico e screenshot

**What to build:** Creare una rete automatica che rilevi regressioni responsive prima della build Android e produca screenshot confrontabili dei profili supportati.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 09 — Implementare fondazione Material e preferenze

**Status:** blocked-dependency

- [ ] Il harness copre almeno 400dp compatto, tablet portrait, tablet landscape simulato e desktop Windows.
- [ ] Ogni profilo viene verificato a scala standard e 130%.
- [ ] Gli assert rilevano widget fuori bounds, sovrapposizioni, larghezze nulle, testo tagliato e target sotto il minimo.
- [ ] Gli screenshot baseline sono deterministici e aggiornabili con un comando documentato.
- [ ] Rotazione, reflow e cambio scala possono essere esercitati nella stessa sessione di test.
- [ ] L'infrastruttura distingue failure geometrica da semplice differenza visiva.
