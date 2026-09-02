# 12 — Dismissione Streamlit + skill agente CSV

**What to build:** Con l'app Kivy a parità funzionale: rimozione di `app.py` e della dipendenza Streamlit da requirements; la skill `genera-csv-scheda` (o nuova skill/plugin) diventa l'entry point ufficiale per il flusso agente Cowork: genera il CSV/manifest iniziale che l'utente importa nell'app (PC o Android) per creare la scheda. CLAUDE.md riscritto per il nuovo assetto: app Kivy come unica UI, core come unica logica, skill come entry point agente.

**Blocked by:** 08 — Generazione Google Doc (parità funzionale raggiunta)

**Status:** blocked-dependency

**Blocco attuale:** richiede la parita' funzionale del ticket 08, che non puo'
essere verificata finche' il login Android del ticket 01 resta bloccato.

- [ ] `app.py` e dipendenza Streamlit rimossi
- [ ] Skill agente per generazione CSV/manifest aggiornata e funzionante
- [ ] CLAUDE.md riscritto per il nuovo assetto (Kivy + core + skill)
- [ ] README aggiornato (installazione, build, uso)
- [ ] Test suite verde
