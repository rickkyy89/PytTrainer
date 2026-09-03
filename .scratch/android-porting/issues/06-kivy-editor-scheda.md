# 06 — App Kivy: editor scheda

**What to build:** Schermata editor completa della scheda: modifica di tutti i campi esercizio (nome, spiegazione, note, ripetizioni, recupero, gruppo), aggiunta/rimozione/riordino esercizi, gestione gruppi con completamento da esistenti, import esercizi da CSV e da un'altra scheda (con scelta sostituisci/aggiungi), segnalazione slug duplicati, indicatore di modifiche non salvate. Salvataggio → `salva_scheda` + upload su Drive. File picker di piattaforma (plyer su Android, dialogo nativo su PC), niente tkinter.

**Blocked by:** 05 — App Kivy: lista schede

**Status:** in-progress

**Implementato nel codice:** `kivy_app/editor.py` (SchedaEditorController,
testato: editing campi, aggiungi/rimuovi/sposta, gruppi esistenti +
completamento, import CSV/scheda con sostituisci/aggiungi, duplicati slug,
indicatore sporco, salva atomico + upload con conflitto propagato) e
`kivy_app/editor_screen.py` (UI Kivy) agganciata alla home tramite il nuovo
`DriveHomeController.open_for_edit`/`import_remote_into`. File picker di
piattaforma in `kivy_app/file_picker.py` (win32 GetOpenFileNameW via ctypes,
FileChooser Kivy altrove, niente tkinter). `kivy` aggiunto a requirements.txt.
106 test verdi, smoke import UI su PC ok.

**Residuo:** verifica manuale dell'editor su PC (finestra reale) e su
dispositivo Android, che dipende dalla build/E2E del ticket 05.

- [x] Editing di tutti i campi esercizio incluso gruppo (con completamento)
- [x] Aggiungi/rimuovi/riordina esercizi
- [x] Import da CSV e da altra scheda con scelta sostituisci/aggiungi
- [x] Avviso slug duplicati
- [x] Indicatore modifiche non salvate
- [x] Salvataggio → bundle atomico + upload Drive
- [ ] File picker di piattaforma funzionante su PC e Android (codice pronto, non verificato a mano)
