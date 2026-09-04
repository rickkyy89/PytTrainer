# 04 — Progettare Undo transazionale dei media

**What to build:** Definire come URL, timestamp, crop, import immagini e sostituzione dei frame entrano nella cronologia senza perdere file o consumare spazio senza controllo.

**Agent:** Sol (`senior_coder`)

**Blocked by:** 01 — Progettare transazioni, cronologia e ciclo di salvataggio

**Status:** completed

- [x] Il contratto specifica snapshot, ownership, durata e cleanup dei file necessari a undo/redo.
- [x] Crop ripetuti, sostituzioni e frame mancanti sono reversibili fino al checkpoint locale.
- [x] Il limite globale di 20 azioni vale anche per le operazioni media e libera gli snapshot espulsi.
- [x] Errori a metà operazione non lasciano manifest e file frame in stati discordanti.
- [x] Salvataggio, Scarta, chiusura e riapertura della schermata Media hanno semantiche esplicite.
- [x] La strategia include test con filesystem temporaneo ed è pronta per l'implementazione di Luna.

**Deliverable:** [`../04-contratto-undo-media.md`](../04-contratto-undo-media.md)
