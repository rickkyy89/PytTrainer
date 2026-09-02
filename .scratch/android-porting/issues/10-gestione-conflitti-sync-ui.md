# 10 — Gestione conflitti sync in UI

**What to build:** Quando `core.drive_sync` segnala un conflitto (scheda modificata in locale E remotamente dall'ultimo sync), l'app mostra un dialogo con i timestamp delle due versioni e tre scelte: tieni versione locale (sovrascrive remota), tieni versione remota (sovrascrive locale), duplica (la remota resta e la locale diventa una nuova scheda con nome suffissato). Il controllo avviene all'apertura e al salvataggio di una scheda. Mai last-write-wins silenzioso.

**Blocked by:** 05 — App Kivy: lista schede

**Status:** ready-for-agent

- [ ] Controllo conflitto all'apertura scheda
- [ ] Controllo conflitto al salvataggio
- [ ] Dialogo con timestamp e tre scelte (locale / remota / duplica)
- [ ] Ogni scelta produce l'esito atteso su Drive e in locale
- [ ] Test manuali documentati dello scenario a due dispositivi
