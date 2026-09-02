# 05 — App Kivy: lista schede da Drive

**What to build:** Prima schermata dell'app Kivy (funzionante su PC e Android): home che elenca le schede presenti nella cartella Drive dedicata con nome e data modifica; apertura di una scheda (download + `carica_scheda`) in sola lettura con elenco esercizi e frame; creazione di una nuova scheda vuota (upload su Drive); eliminazione con conferma. Avviso chiaro se offline. Login Google all'avvio con il provider di piattaforma (OAuth browser su PC, Google Sign-In su Android). La navigazione verso l'editor esiste ma l'editing arriva nel ticket successivo.

**Blocked by:** 01 — Spike Android; 04 — `core.drive_sync`

**Status:** in-progress

**Implementato nel codice:** home Kivy PC con controller testabile, cartelle
Drive locali persistenti (iniziale `1UthYZdR1GiVADYNUWBN1cX3z790FEkXq`),
lista/refresh, download e lettura sola, creazione/upload, conferma
eliminazione e stato Drive non disponibile. La composizione PC usa
`LocalCredentialsProvider` e la build del client Drive in modo lazy/iniettabile.

**Blocco residuo:** la verifica su dispositivo, la build Android e l'OAuth di
produzione restano da fare. Il client dello spike (`org.ptt.pttspike` con SHA-1
debug) non e' riusabile: il package di produzione deve essere esattamente
`org.ptt.pyTrainer`, con client OAuth Android e certificato release registrati.

- [x] Home con lista schede da Drive (nome + data modifica), aggiornabile
- [x] Apertura scheda in sola lettura: esercizi e frame visibili
- [x] Creazione nuova scheda vuota sincronizzata su Drive
- [x] Eliminazione scheda con conferma
- [x] Avviso offline visibile
- [ ] Login Google funzionante su PC e su Android
- [ ] App avviabile su PC e installabile su Android (build interna)
