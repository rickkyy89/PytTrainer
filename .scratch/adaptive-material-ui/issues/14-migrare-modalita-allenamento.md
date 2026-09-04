# 14 — Migrare Modalità Allenamento

**What to build:** Offrire una modalità allenamento leggibile a distanza e comoda al touch, dando priorità all'esercizio corrente senza perdere avanzamento e timer.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 09 — Implementare fondazione Material e preferenze; 10 — Costruire harness geometrico e screenshot

**Status:** completed

- [x] L'esercizio corrente domina la gerarchia con nome, ripetizioni, recupero e frame chiaramente leggibili.
- [x] Timer, avanzamento e azioni restano raggiungibili durante lo scroll.
- [x] START e FINISH cambiano disposizione in base al profilo senza diventare troppo piccoli.
- [x] Controlli touch, checkbox e pulsanti rispettano almeno 48dp su Android.
- [x] Testo lungo e scala 130% non si sovrappongono né vengono tagliati.
- [x] Il comportamento funzionale preesistente dell'allenamento resta invariato.

**Deliverable:** `kivy_app/workout_layout.py`, integrazione in `kivy_app/workout_screen.py` e `tests/test_workout_layout.py`
