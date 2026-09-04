# 05 — Implementare Undo/Redo dei media

**What to build:** Integrare tutte le modifiche Video/Frame nella cronologia della scheda, inclusi i file immagine, mantenendo coerenti anteprime, manifest e stato dell'editor.

**Agent:** Luna (`junior_coder`)

**Blocked by:** 02 — Implementare Undo/Redo dell'editor; 04 — Progettare Undo transazionale dei media

**Status:** ready-for-agent

- [ ] URL e timestamp possono essere annullati e ripristinati.
- [ ] Crop, import immagine e sostituzione frame ripristinano anche i contenuti dei file corretti.
- [ ] Navigare tra Editor e Media conserva una sola cronologia coerente.
- [ ] Checkpoint locale, Scarta e limite di 20 azioni puliscono gli snapshot non più necessari.
- [ ] Un errore durante un'operazione media mantiene intatto lo stato precedente.
- [ ] I test automatici usano file reali temporanei e verificano contenuto, non solo presenza.
