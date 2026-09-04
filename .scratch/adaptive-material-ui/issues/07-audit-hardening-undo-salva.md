# 07 — Audit e hardening di Undo/Salva

**What to build:** Validare le invarianti del nuovo ciclo di editing e risolvere alla radice eventuali bug difficili emersi dopo il primo passaggio Luna.

**Agent:** Sol (`senior_coder`)

**Blocked by:** 06 — Integrare e correggere il primo passaggio editing

**Status:** blocked-dependency

- [ ] L'audit verifica atomicità, ownership degli snapshot, cleanup e coerenza tra manifest e frame.
- [ ] Dirty state, checkpoint locale, sync Drive e cronologia rispettano il contratto del ticket 01.
- [ ] Ogni bug residuo è accompagnato da una riproduzione automatica prima della correzione quando fattibile.
- [ ] Le correzioni sono root-cause e non introducono percorsi di compatibilità non richiesti.
- [ ] La suite completa passa e non rimangono failure mode ad alta severità senza decisione esplicita.
