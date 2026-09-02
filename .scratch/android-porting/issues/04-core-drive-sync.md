# 04 — `core.drive_sync`: lista, download, upload, rilevamento conflitti

**What to build:** Nuovo modulo del core che sincronizza i file `.scheda` con la cartella dedicata su Google Drive (ID cartella in configurazione, non hardcoded). Espone: lista delle schede remote (nome, id, timestamp modifica), download di una scheda nella cache locale registrando il timestamp remoto dell'ultimo sync, upload di una scheda nuova o modificata, creazione ed eliminazione di schede nella cartella. Rilevamento conflitto: copia locale modificata E copia remota più recente dell'ultimo sync → il modulo espone il conflitto con entrambi i timestamp, senza decidere (la scelta è dell'utente via UI). Sempre online: nessuna coda offline. Testato interamente contro un fake client Drive, nessuna chiamata di rete reale nei test.

**Blocked by:** 02 — Estrarre package `core`

**Status:** ready-for-agent

- [ ] Lista schede dalla cartella Drive con nome/id/timestamp modifica
- [ ] Download scheda in cache locale con tracciamento timestamp ultimo sync
- [ ] Upload scheda nuova o modificata
- [ ] Creazione ed eliminazione schede nella cartella Drive
- [ ] Rilevamento conflitto (locale modificata + remota più recente) esposto con entrambi i timestamp, senza auto-risoluzione
- [ ] ID cartella Drive in configurazione
- [ ] Test pytest su fake client Drive: lista, download, upload, conflitto sì/no, eliminazione
