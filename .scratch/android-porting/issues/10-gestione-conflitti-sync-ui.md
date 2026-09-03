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

**Fix di review applicati (2026-09-03):** `resolve_conflict` accetta il
`local_path` aperto (una rinomina remota non rompe piu' locale/duplicata);
`_duplicate_path` sceglie il suffisso evitando sia i nomi remoti esistenti
(`list_schede`) sia la cache; il dialogo risolve in un worker thread con
pulsanti disabilitati (niente congelamento UI/ANR); dopo remota/duplicata
dall'editor si torna alla LISTA aggiornata con messaggio sulla home
(`go_home_message`), non su un widget smontato.

**Limiti noti documentati:** (a) tra apertura dialogo e "tieni locale" una
nuova modifica remota cadrebbe schiacciata senza ri-mostra: servirebbero
ETag/If-Match su Drive (il conflitto mostrato richiede comunque una scelta
esplicita, quindi non e' un last-write-wins silenzioso); (b) "duplicata" non
e' atomica: se il download finale fallisce dopo la creazione della copia, un
retry crea una seconda copia suffissata.

**Residuo:** verifica del dialog e del flusso di conflitto su dispositivo
Android (lato PC completato, vedi sotto).

**Verifica "due dispositivi" completata (2026-09-03, script
`.scratch/verify_conflict_10.py`, Drive reale):** tre controller con
cache separate (A/B/C) simulano i dispositivi su una scheda di test
"TEST VERIFICA 10.scheda" creata e distrutta dallo script (nessun
impatto sulle schede utente). Esiti:
- conflitto al salvataggio: `editor.salva()` restituisce `SyncConflict`
  senza caricare (niente last-write-wins silenzioso);
- risoluzione "locale": upload forzato, il remoto diventa la versione B;
- risoluzione "remota": la cache B viene riallineata al remoto e la
  modifica locale risulta scartata;
- check all'apertura: `controller.check_conflict` rileva il conflitto in
  corso SENZA download;
- risoluzione "duplicata": copia "TEST VERIFICA 10 (2).scheda" con la
  versione B, originale riallineato alla versione A, conflitto chiuso
  (`check_conflict` ritorna None dopo ciascuna risoluzione);
- cleanup: schedine di test eliminate da Drive, cache rimosse.
Script idempotente (pre-cleanup dei residui di esecuzioni interrotte).
Nota: il dialog Kivy a tre scelte è coperto da tests/test_kivy_conflict.py
(logica); la resa visiva su dispositivo resta nel residuo Android.

- [x] Controllo conflitto all'apertura scheda
- [x] Controllo conflitto al salvataggio
- [x] Dialogo con timestamp e tre scelte (locale / remota / duplica)
- [x] Ogni scelta produce l'esito atteso su Drive e in locale
- [x] Test manuali documentati dello scenario a due dispositivi
