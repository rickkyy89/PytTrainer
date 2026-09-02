# 05 — App Kivy: lista schede da Drive

**What to build:** Prima schermata dell'app Kivy (funzionante su PC e Android): home che elenca le schede presenti nella cartella Drive dedicata con nome e data modifica; apertura di una scheda (download + `carica_scheda`) in sola lettura con elenco esercizi e frame; creazione di una nuova scheda vuota (upload su Drive); eliminazione con conferma. Avviso chiaro se offline. Login Google all'avvio con il provider di piattaforma (OAuth browser su PC, Google Sign-In su Android). La navigazione verso l'editor esiste ma l'editing arriva nel ticket successivo.

**Blocked by:** 01 — Spike Android; 04 — `core.drive_sync`

**Status:** in-progress

**Implementato nel codice:** home Kivy PC con controller testabile, cartelle
Drive locali persistenti (iniziale `1UthYZdR1GiVADYNUWBN1cX3z790FEkXq`),
lista/refresh, download e lettura sola, creazione/upload, conferma
eliminazione e stato Drive non disponibile. La composizione PC usa
`LocalCredentialsProvider` e la build del client Drive in modo lazy/iniettabile.

**Blocco residuo:** la verifica su dispositivo e l'OAuth di produzione restano
da fare. Il client dello spike (`org.ptt.pttspike`) non e' riusabile: in Google
Cloud va aggiunto un client OAuth Android per il package esatto
`org.ptt.pyTrainer`, usando per la build debug questo SHA-1:

```text
BC:F1:89:B3:03:20:ED:2D:2B:07:CA:C9:5D:B1:0C:6D:C9:B2:D2:E1
```

La prima build debug con `buildozer -v android debug` ha raggiunto la
compilazione di OpenSSL ma e' stata interrotta dal limite temporale
dell'ambiente prima di generare l'APK; la cache `.buildozer/` permette di
riprenderla.

- [x] Home con lista schede da Drive (nome + data modifica), aggiornabile
- [x] Apertura scheda in sola lettura: esercizi e frame visibili
- [x] Creazione nuova scheda vuota sincronizzata su Drive
- [x] Eliminazione scheda con conferma
- [x] Avviso offline visibile
- [ ] Login Google funzionante su PC e su Android
- [ ] App avviabile su PC e installabile su Android (build interna)
