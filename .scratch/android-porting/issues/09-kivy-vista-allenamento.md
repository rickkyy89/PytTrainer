# 09 — App Kivy: vista allenamento

**What to build:** Modalità "in palestra": per la scheda aperta, vista a scorrimento con per ogni esercizio frame START/FINISH grandi, nome, ripetizioni, recupero e note ben leggibili; checkbox per spuntare gli esercizi completati (stato di sessione, non persistito nel bundle); timer di recupero avviabile con durata presa dal campo Recupero, con avviso a fine countdown. Layout pensato per uso con una mano sul telefono.

**Blocked by:** 06 — App Kivy: editor scheda

**Status:** blocked-dependency

**Blocco attuale:** richiede l'editor Kivy del ticket 06, a sua volta bloccato
dalla home del ticket 05 e dalla validazione OAuth Android del ticket 01.

- [ ] Vista con frame grandi + nome/ripetizioni/recupero/note per ogni esercizio
- [ ] Spunta esercizi completati (solo sessione)
- [ ] Timer recupero con durata dal campo Recupero e avviso a fine countdown
- [ ] Usabile su telefono con una mano
