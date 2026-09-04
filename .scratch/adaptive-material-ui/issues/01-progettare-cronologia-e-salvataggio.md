# 01 — Progettare transazioni, cronologia e ciclo di salvataggio

**What to build:** Definire il contratto implementabile che rende reversibili le modifiche della scheda e distingue chiaramente stato in memoria, checkpoint locale e sincronizzazione Drive. Il risultato deve permettere a Luna di implementare editor e media senza riaprire decisioni architetturali.

**Agent:** Sol (`senior_coder`)

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] Il modello descrive comandi, undo, redo, nuova modifica dopo undo e limite FIFO di 20 azioni.
- [ ] Sono definite le invarianti di modifiche non salvate, copia locale più recente e copia Drive sincronizzata.
- [ ] È precisato che un checkpoint locale riuscito azzera la cronologia anche se il successivo upload Drive fallisce.
- [ ] Sono definite le semantiche di Salva, Scarta, Resta e ripristino dell'ultimo checkpoint.
- [ ] L'interfaccia condivisa copre modifiche testuali, strutturali e media senza esporre dettagli Kivy.
- [ ] Una matrice di test e failure mode accompagna il contratto per il passaggio a Luna.
