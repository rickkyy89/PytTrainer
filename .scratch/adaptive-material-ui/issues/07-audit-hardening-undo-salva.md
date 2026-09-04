# 07 — Audit e hardening di Undo/Salva

**What to build:** Validare le invarianti del nuovo ciclo di editing e risolvere alla radice eventuali bug difficili emersi dopo il primo passaggio Luna.

**Agent:** Sol (`senior_coder`)

**Blocked by:** 06 — Integrare e correggere il primo passaggio editing

**Status:** completed

- [x] L'audit verifica atomicità, ownership degli snapshot, cleanup e coerenza tra manifest e frame.
- [x] Dirty state, checkpoint locale, sync Drive e cronologia rispettano il contratto del ticket 01.
- [x] Ogni bug residuo è accompagnato da una riproduzione automatica prima della correzione quando fattibile.
- [x] Le correzioni sono root-cause e non introducono percorsi di compatibilità non richiesti.
- [x] La suite completa passa e non rimangono failure mode ad alta severità senza decisione esplicita.
