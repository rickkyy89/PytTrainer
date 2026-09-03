# 09 — App Kivy: vista allenamento

**What to build:** Modalità "in palestra": per la scheda aperta, vista a scorrimento con per ogni esercizio frame START/FINISH grandi, nome, ripetizioni, recupero e note ben leggibili; checkbox per spuntare gli esercizi completati (stato di sessione, non persistito nel bundle); timer di recupero avviabile con durata presa dal campo Recupero, con avviso a fine countdown. Layout pensato per uso con una mano sul telefono.

**Blocked by:** 06 — App Kivy: editor scheda

**Status:** in-progress

**Implementato nel codice (2026-09-03):** `kivy_app/workout.py`
(`WorkoutSessionController`, testato con clock iniettato: spunte solo di
sessione con toggle/azzera, parsing `Recupero` ("90 SEC", "1:30", "2 min",
"90s", ... -> secondi, default 60 se illeggibile), countdown con
avvia/annulla/scaduto). `kivy_app/workout_screen.py` (UI: card scrollabili
con frame START/FINISH grandi, nome/ripetizioni/recupero/note, CheckBox,
barra timer fissa in basso per uso con una mano, tick via Clock e avviso a
fine countdown). `kivy_app/notify.py`: beep (winsound) su PC, vibrazione/notifica
(plyer) su Android, sempre guardato. `DriveHomeController.open_for_workout`
scarica e passa i dizionari esercizi senza percorso di salvataggio (stato di
sessione, niente persistenza nel bundle). Ingresso "Allenati" dalla scheda in
sola lettura.

**Residuo:** verifica su dispositivo (tasti grandi/una mano, vibrazione) e
con frame reali.

- [x] Vista con frame grandi + nome/ripetizioni/recupero/note per ogni esercizio
- [x] Spunta esercizi completati (solo sessione)
- [x] Timer recupero con durata dal campo Recupero e avviso a fine countdown
- [x] Usabile su telefono con una mano (layout; da confermare su dispositivo)
