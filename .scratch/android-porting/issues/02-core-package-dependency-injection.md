# 02 — Estrarre package `core` con dependency injection delle 3 astrazioni

**What to build:** I quattro moduli di dominio esistenti (scheda_file, csv_utils, video_helper, google_docs_helper→docs_helper) diventano un package `core` importabile, privo di qualsiasi dipendenza UI e di qualsiasi path relativo alla working directory. Tre astrazioni iniettate dal chiamante: (1) base directory per credenziali/token/cache `.work`, (2) backend ffmpeg (implementazione PC: binario di sistema via subprocess, con fallback anti-403 esistente), (3) provider credenziali Google (implementazione PC: service account oppure OAuth browser con token cache, incluso flusso manuale headless). Le API pubbliche restano quelle documentate in CLAUDE.md (stesse firme, stesso comportamento); il formato `.scheda` e lo `state.json` sono invariati. L'app Streamlit esistente viene aggiornata per importare dal package `core` e continua a funzionare identica. I test esistenti (test_scheda_file, test_smoke) sono migrati sul package e verdi.

**Blocked by:** 01 — Spike Android (le ricette/build flags emerse dalla spike possono influenzare le astrazioni, es. firma del backend ffmpeg)

**Status:** done

- [x] Package `core` importabile con i quattro moduli e API pubbliche invariate
- [x] Nessun path CWD-relativo nel core: base directory sempre esplicita per i chiamanti nuovi
- [x] Backend ffmpeg iniettato con implementazione PC (subprocess) funzionante
- [x] Provider credenziali iniettato con implementazione PC (OAuth browser + token cache + flusso manuale)
- [x] Test esistenti migrati sul package `core` e tutti verdi
- [x] App Streamlit aggiornata sopra il `core`; test funzionale manuale resta disponibile
- [x] CLAUDE.md aggiornato con i nuovi import
