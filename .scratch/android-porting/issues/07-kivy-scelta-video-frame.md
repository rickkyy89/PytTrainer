# 07 — App Kivy: scelta video e frame

**What to build:** Per ogni esercizio, schermata video & frame con parità funzionale rispetto alla tab "🎬 Video & Frame" di Streamlit: ricerca YouTube (top 3 con titolo/durata/anteprima), selezione risultato o URL manuale, timestamp START/FINISH con proposta euristica, estrazione frame sul device (backend ffmpeg di piattaforma), anteprime frame, crop per lati in percentuale con anteprima e ripristino dal backup `_orig.jpg`, import di un'immagine propria dalla galleria (Android) o dal filesystem (PC) come frame START/FINISH. `scegli_ed_estrai` rispetta le scelte già presenti nel manifest (idempotenza).

**Blocked by:** 06 — App Kivy: editor scheda

**Status:** in-progress

**Implementato nel codice (2026-09-03):** `kivy_app/media.py`
(`MediaFlowController`, testato senza rete/Kivy: ricerca+filtro pertinenza
con log scarti, selezione risultato, URL manuale, euristica 10%/50%,
estrazione idempotente con `riestrai` forzato, validazione finish>start,
crop con backup `_orig.jpg` + anteprima live su file temporaneo + ripristino,
import immagine). `kivy_app/media_screen.py` (UI Kivy con ricerca/estrazione
in worker thread e reentrancy guard). Seam `core.video_helper.extract_frame`:
rileva un backend con metodo `extract(...)` e salta ffmpeg (niente cambio per
i chiamanti esistenti; `PcFfmpegBackend` invariato).
`kivy_app.platform_android.AndroidFrameExtractor`: estrazione nativa via
`MediaMetadataRetriever` (rischio 2b dello spike), classi Java cachate al
main thread, jnius risolto solo in `__init__`. Navigazione editor→media→
editor che conserva l'editor live e marca dirty (`marca_modifica`).

**Fix di review applicati:** eccezioni asincrone materializzate prima del
ritorno al main thread; back button disabilitato durante l'operazione in
corso (niente Salva concorrente con il worker); idempotenza estrazione;
validation ordine timestamp come Streamlit; `_crop_preview_*` non finisce nel
bundle (salva_scheda include solo frame del manifest + `_orig`).

**Residuo:** verifica su dispositivo Android (estrazione MMR reale su
YouTube, picker/SAF galleria) e smoke UI con rete, entrambe dipendenti dal
dispositivo del ticket 05.

- [x] Ricerca YouTube con risultati (titolo, durata, anteprima) e selezione
- [x] URL video manuale override
- [x] Timestamp START/FINISH con euristica 10%/50%
- [ ] Estrazione frame sul device su PC e Android (PC ok, Android: codice pronto, da validare su dispositivo)
- [x] Crop per lati con anteprima, applica e ripristina da backup `_orig.jpg`
- [x] Import immagine propria come frame START/FINISH (galleria Android / filesystem PC)
- [x] Idempotenza: scelte gia' nel manifest non ri-estratte
- [x] Frame salvati nel bundle e sincronizzati su Drive al salvataggio
