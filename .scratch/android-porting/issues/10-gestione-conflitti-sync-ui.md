# 10 — Gestione conflitti sync in UI

**What to build:** Quando `core.drive_sync` segnala un conflitto (scheda modificata in locale E remotamente dall'ultimo sync), l'app mostra un dialogo con i timestamp delle due versioni e tre scelte: tieni versione locale (sovrascrive remota), tieni versione remota (sovrascrive locale), duplica (la remota resta e la locale diventa una nuova scheda con nome suffissato). Il controllo avviene all'apertura e al salvataggio di una scheda. Mai last-write-wins silenzioso.

**Blocked by:** 05 — App Kivy: lista schede

**Status:** in-progress

**Implementato nel codice (2026-09-03):** `core.drive_sync` espone
`check_conflict(local_path, file_id)` (sola lettura; nessun file locale =
nessun conflitto) e `upload_scheda(..., force=True)` per la scelta "tieni
locale". `DriveHomeController.check_conflict(remote)` controlla la cache senza
download e `resolve_conflict(conflict, choice)` applica le tre scelte:
`locale` = upload forzato sul file id aperto; `remota` = riscaricamento che
scarta le modifiche locali; `duplicata` = copia locale caricata su Drive con
nome suffissato "(2)/(3)/..." e ripristino dell'originale dalla remota (il
conflitto non puo' rigenerarsi). Dialogo Kivy condiviso
`kivy_app/conflict_dialog.py` con entrambi i timestamp e i tre pulsanti;
agganciato all'apertura scheda (home) e al salvataggio (editor, con
`editor.conferma_salvataggio()` e ritorno alla lista quando l'editor in
memoria non coincide piu' col disco). Mai last-write-wins silenzioso.

**Residuo:** prova manuale su due device/browser con Drive reale.

- [x] Controllo conflitto all'apertura scheda
- [x] Controllo conflitto al salvataggio
- [x] Dialogo con timestamp e tre scelte (locale / remota / duplica)
- [x] Ogni scelta produce l'esito atteso su Drive e in locale
- [ ] Test manuali documentati dello scenario a due dispositivi
