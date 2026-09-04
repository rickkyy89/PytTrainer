# 03 — Unificare Salva e proteggere l'uscita

**What to build:** Sostituire i due salvataggi con un solo comando che chiede Locale o Drive e impedire l'uscita accidentale quando esistono modifiche non salvate.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 01 — Progettare transazioni, cronologia e ciclo di salvataggio; 02 — Implementare Undo/Redo dell'editor

**Status:** blocked-dependency

- [ ] Salva mostra sempre le scelte Locale e Drive; Drive salva prima il bundle locale e poi esegue l'upload.
- [ ] Un checkpoint locale riuscito azzera undo/redo; un upload fallito lascia visibile lo stato da sincronizzare.
- [ ] Il valore del campo attivo viene acquisito prima di salvare o uscire.
- [ ] Indietro con modifiche mostra Salva, Scarta e Resta; Scarta ripristina il checkpoint prima di uscire.
- [ ] Pulsante UI, gesto/tasto Android Back e chiusura Windows rispettano la stessa protezione quando tecnicamente intercettabili.
- [ ] `Ctrl+S`, `Ctrl+Z`, `Ctrl+Y` e `Ctrl+Shift+Z` funzionano su Windows.
- [ ] Stato persistente ed esiti contestuali distinguono modifiche, salvataggio locale e sincronizzazione Drive.
