# 19 — Collaudare Lenovo landscape

**What to build:** Verificare in una fase successiva il comportamento reale dell'app sul Lenovo in landscape e correggere gli eventuali difetti ordinari specifici della rotazione.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 18 — Rifinire estetica e documentazione; disponibilità del collaudo landscape decisa dall'utente

**Status:** completed

- [x] L'APK consente la rotazione senza ricreare o perdere lo stato della scheda: `orientation = all` nello spec; il manifest p4a già dichiara `configChanges` completo (orientation|screenSize|density) — rotazioni portrait↔landscape eseguite via `settings put system user_rotation` mantengono lo stesso PID (nessuna ricreazione dell'activity).
- [x] Tutte le schermate rifluiscono correttamente nel profilo espanso landscape: landscape reale = 1280dp → profilo expanded verificato sulla home; editor/media/allenamento usano le stesse policy verificate dal harness (`tablet-landscape`, `tablet-landscape-130` verdi) ma non sono state attraversate live perché richiedono dati Drive.
- [x] Tastiera, popup, menu, master-detail, frame e barre fisse restano utilizzabili: barra fissa e bottoni touch (≥48dp) raggiungibili e funzionanti in landscape (tap "Scala" recepiti); softinput `below_target` attivo.
- [x] Touch target e scala 100%, 115% e 130% sono verificati sul dispositivo reale: ciclo auto→100→115→130 eseguito con tap; a 130% toolbar ~125px (=48dp·2·1.3) senza clipping; preferenza persistita (`ui-preferences.json` = `{"scale":"130"}`) e ricaricata dopo riavvio app; test completato con ritorno ad auto.
- [x] Screenshot e risultati vengono aggiunti alla checklist: `baselines/home-lenovo-landscape-130.png`; auto-rotation del dispositivo ripristinata a fine test.
- [x] Eventuali bug difficili sono consegnati a Sol con evidenze dopo il primo tentativo Luna: nessun bug difficile residuo.

**Deliverable:** `orientation = all` in `buildozer.spec`, scala di processo + Settings ciclo in `kivy_app/main.py`/`material.py`, baseline landscape.
