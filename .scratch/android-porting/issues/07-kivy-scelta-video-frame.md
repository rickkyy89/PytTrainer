# 07 — App Kivy: scelta video e frame

**What to build:** Per ogni esercizio, schermata video & frame con parità funzionale rispetto alla tab "🎬 Video & Frame" di Streamlit: ricerca YouTube (top 3 con titolo/durata/anteprima), selezione risultato o URL manuale, timestamp START/FINISH con proposta euristica, estrazione frame sul device (backend ffmpeg di piattaforma), anteprime frame, crop per lati in percentuale con anteprima e ripristino dal backup `_orig.jpg`, import di un'immagine propria dalla galleria (Android) o dal filesystem (PC) come frame START/FINISH. `scegli_ed_estrai` rispetta le scelte già presenti nel manifest (idempotenza).

**Blocked by:** 06 — App Kivy: editor scheda

**Status:** ready-for-agent

- [ ] Ricerca YouTube con risultati (titolo, durata, anteprima) e selezione
- [ ] URL video manuale override
- [ ] Timestamp START/FINISH con euristica 10%/50%
- [ ] Estrazione frame sul device su PC e Android
- [ ] Crop per lati con anteprima, applica e ripristina da backup `_orig.jpg`
- [ ] Import immagine propria come frame START/FINISH (galleria Android / filesystem PC)
- [ ] Idempotenza: scelte già nel manifest non ri-estratte
- [ ] Frame salvati nel bundle e sincronizzati su Drive al salvataggio
