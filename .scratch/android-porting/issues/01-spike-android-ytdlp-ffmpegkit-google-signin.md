# 01 — Spike Android: yt-dlp + ffmpeg-kit + Google Sign-In

**What to build:** Un'app Kivy minima throwaway, buildata con buildozer e installata su un dispositivo Android reale (Android 10+), che dimostra i tre rischi tecnici del porting: (1) ricerca YouTube con yt-dlp come libreria Python sul device, (2) estrazione di un frame JPEG a un timestamp dato da uno stream video usando ffmpeg-kit, (3) login Google con il flusso nativo (Google Sign-In) che ottiene credenziali valide per gli scope Drive/Docs. L'app mostra a schermo l'esito delle tre operazioni. Non è richiesto alcun legame col codice PytTrainer: serve a chiudere i rischi prima del refactor.

**Blocked by:** None — can start immediately

**Status:** in-progress

- [x] APK buildato con buildozer e installato su dispositivo reale Android 10+
- [x] Ricerca yt-dlp sul device ritorna risultati (titolo/durata/URL) per una query di prova
- [x] Estrazione di un frame JPEG da uno stream YouTube a un timestamp dato, salvato e mostrato a schermo
- [ ] Login Google nativo completato con credenziali valide per scope `drive.file` e `documents`
- [ ] Documentati nel repo (nota in docs/) ricetta buildozer.spec, ricette/pacchetti necessari, dimensioni APK e problemi incontrati

## Implementazione in corso

Lo spike include `GoogleBridge`, un bridge Java minimo che usa `AuthorizationClient`
per richiedere gli scope `drive.file` e `documents`. Il pulsante Drive Picker usa
`ACTION_OPEN_DOCUMENT`, che apre il provider Drive del sistema e restituisce una
`content://` URI. Il token non viene scritto nei log.

Per completare il test reale occorre registrare in Google Cloud un client OAuth
Android con package `org.ptt.pttspike` e SHA-1 debug:

```text
BC:F1:89:B3:03:20:ED:2D:2B:07:CA:C9:5D:B1:0C:6D:C9:B2:D2:E1
```
