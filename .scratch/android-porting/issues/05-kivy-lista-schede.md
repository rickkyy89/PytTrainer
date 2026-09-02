# 05 — App Kivy: lista schede da Drive

**What to build:** Prima schermata dell'app Kivy (funzionante su PC e Android): home che elenca le schede presenti nella cartella Drive dedicata con nome e data modifica; apertura di una scheda (download + `carica_scheda`) in sola lettura con elenco esercizi e frame; creazione di una nuova scheda vuota (upload su Drive); eliminazione con conferma. Avviso chiaro se offline. Login Google all'avvio con il provider di piattaforma (OAuth browser su PC, Google Sign-In su Android). La navigazione verso l'editor esiste ma l'editing arriva nel ticket successivo.

**Blocked by:** 01 — Spike Android; 04 — `core.drive_sync`

**Status:** blocked-user

**Blocco attuale:** il login Google nativo su Android (ticket 01) non e' stato
validato: manca la configurazione del client OAuth Android nel progetto Google
Cloud. Senza credenziali valide non e' possibile verificare la home con Drive
su un dispositivo reale.

- [ ] Home con lista schede da Drive (nome + data modifica), aggiornabile
- [ ] Apertura scheda in sola lettura: esercizi e frame visibili
- [ ] Creazione nuova scheda vuota sincronizzata su Drive
- [ ] Eliminazione scheda con conferma
- [ ] Avviso offline visibile
- [ ] Login Google funzionante su PC e su Android
- [ ] App avviabile su PC e installabile su Android (build interna)
