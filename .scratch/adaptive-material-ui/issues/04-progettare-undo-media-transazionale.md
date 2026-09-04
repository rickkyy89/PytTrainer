# 04 — Progettare Undo transazionale dei media

**What to build:** Definire come URL, timestamp, crop, import immagini e sostituzione dei frame entrano nella cronologia senza perdere file o consumare spazio senza controllo.

**Agent:** Sol (`senior_coder`)

**Blocked by:** 01 — Progettare transazioni, cronologia e ciclo di salvataggio

**Status:** blocked-dependency

- [ ] Il contratto specifica snapshot, ownership, durata e cleanup dei file necessari a undo/redo.
- [ ] Crop ripetuti, sostituzioni e frame mancanti sono reversibili fino al checkpoint locale.
- [ ] Il limite globale di 20 azioni vale anche per le operazioni media e libera gli snapshot espulsi.
- [ ] Errori a metà operazione non lasciano manifest e file frame in stati discordanti.
- [ ] Salvataggio, Scarta, chiusura e riapertura della schermata Media hanno semantiche esplicite.
- [ ] La strategia include test con filesystem temporaneo ed è pronta per l'implementazione di Luna.
