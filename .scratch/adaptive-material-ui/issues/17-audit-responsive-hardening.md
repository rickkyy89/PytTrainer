# 17 — Audit responsive e hardening cross-device

**What to build:** Riesaminare l'integrazione adattiva e risolvere i problemi difficili di densità, layout, focus, tastiera, rendering o packaging che resistono al primo ciclo Luna.

**Agent:** Sol (`senior_coder`)

**Blocked by:** 16 — Integrare, compilare e correggere il primo passaggio UI

**Status:** completed

- [x] Nessuna schermata bypassa il modulo adattivo con euristiche locali o unità fisiche non motivate: le quattro schermate non hardcodano più `input_mode="touch"` (risolto dal launcher via `input_mode_for_platform`), `main._ui_profile` usa `profile_for_window` senza leggere `Window.density`, l'euristica colonne dell'editor è centralizzata in `editor_layout.field_columns`; restano `input_mode` espliciti solo nelle fixture del harness (intenzionali).
- [x] Il cambio profilo, scala e orientamento simulato mantiene stato e geometria validi: profilo e policy sono funzioni pure delle metriche iniettate (test `profile_for_window` con window finta, scenari rotazione/scale nel harness).
- [x] Sono analizzati e corretti alla radice i difetti residui documentati da Luna: `profile_for_window` mancante (ImportError device), ramo `if/else` identico in `_render_lista`, doppio `return block` in `_exercise_block`, proprietà `Slider.slider_color`/`background_color` inesistenti in Kivy 2.3.1 che avrebbero crashato il tema, master-detail "shell" senza master (ora lista schede a larghezza fissa accanto al dettaglio).
- [x] Focus, tastiera, scroll annidati e viewer immagini non causano controlli irraggiungibili: `Window.softinput_mode="below_target"` applicato dal tema (il campo attivo resta sopra la tastiera e la barra Undo/Redo/Salva è raggiungibile), scroll annidato media già bloccato sugli slider, viewer fullscreen Scatter+Carousel.
- [x] Tema e primitive restano un modulo profondo con interfaccia ridotta e testabile: `material.py` senza Kivy (profilo, token, scala, piano), `theme.py` unico adapter che tocca gli stili di classe Kivy, `primitive_specs` invariato.
- [x] Suite, harness e build APK passano dopo le correzioni: `220 passed`, `compileall` OK, APK ricostruito in WSL e rilanciato sul Lenovo senza crash con tema dark verificato via screenshot; verificato anche il profilo pointer Windows desktop.
