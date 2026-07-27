"""
Funzioni pure per il parsing/validazione del CSV degli esercizi, riusate sia
da app.py che dai test (nessuna dipendenza da Streamlit).

Il CSV funge da manifest persistente della scheda: oltre alle 5 colonne
obbligatorie supporta colonne opzionali (COLONNE_OPZIONALI) che tracciano la
scelta di video, timestamp e frame estratti per ciascun esercizio. Se le
colonne opzionali sono assenti (o vuote), il comportamento resta identico a
quello di un CSV "minimo": ricerca automatica del video ed euristica sui
timestamp.

Implementato con il modulo 'csv' della libreria standard (niente pandas):
sotto Chaquopy (Android) pandas è il pacchetto più pesante e fragile da
impacchettare, e qui serve solo per un CSV di 11 colonne.
"""

from __future__ import annotations

import csv
import io
import re

COLONNE_ATTESE = {"Nome", "Spiegazione", "Note", "Ripetizioni", "Recupero"}

# Colonne opzionali del manifest, nell'ordine in cui vengono scritte da
# scrivi_esercizi_csv(). Se assenti o vuote nel CSV in lettura, si applicano
# i default retrocompatibili (comportamento del CSV a 5 colonne).
COLONNE_OPZIONALI = [
    "Gruppo",
    "VideoURL",
    "TimestampStart",
    "TimestampFinish",
    "FrameStartPath",
    "FrameFinishPath",
]

# Ordine completo delle colonne usato da scrivi_esercizi_csv().
_COLONNE_CSV_COMPLETE = ["Nome", "Spiegazione", "Note", "Ripetizioni", "Recupero"] + COLONNE_OPZIONALI


def slugify(nome: str) -> str:
    """
    Converte un nome (esercizio, titolo scheda, ...) in uno slug sicuro per
    nomi di file/ID (solo [a-z0-9_]). Collocata qui perché riusata sia da
    video_helper (nomi dei file frame) sia da google_docs_helper (nomi dei
    file di stato e dei named range dei documenti).
    """
    slug = nome.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "esercizio"


def _timestamp_o_none(valore, nome_colonna: str) -> float | None:
    """
    Converte una cella di timestamp in float, oppure None se la cella è
    vuota/assente. Solleva ValueError con messaggio chiaro se il valore non è
    numerico.
    """
    if valore is None:
        return None
    testo = str(valore).strip()
    if not testo:
        return None
    try:
        return float(testo)
    except ValueError as exc:
        raise ValueError(
            f"Valore non numerico nella colonna '{nome_colonna}': '{testo}'. "
            "I timestamp devono essere numeri (secondi), es. 12.5."
        ) from exc


def _apri_testo(file_like):
    """
    Normalizza i tre casi d'uso accettati da parse_esercizi_csv() in un
    file-like testuale pronto per csv.DictReader, più un flag che indica se
    va chiuso da noi:

      - percorso stringa: apre il file su disco (utf-8-sig, per tollerare un
        eventuale BOM iniziale; newline="" come raccomandato dal modulo csv);
      - file-like binario (es. io.BytesIO, come lo passa
        scheda_file._estrai_da_zip leggendo il manifest dallo zip) o testuale
        (io.StringIO, un file aperto in modalità testo, o l'oggetto restituito
        da st.file_uploader): ne legge il contenuto e lo travasa in una
        StringIO nostra.

    Il travaso è voluto: avvolgere un file-like altrui in un TextIOWrapper
    significherebbe chiudere anche lo stream sottostante quando chiudiamo il
    wrapper, e app.py passa qui direttamente l'oggetto di st.file_uploader,
    che Streamlit riusa a ogni rerun. Un CSV manifest è piccolo, quindi
    leggerlo tutto in memoria non è un problema.

    Se lo stream è riavvolgibile viene riportato all'inizio prima di leggere:
    senza questo, una seconda chiamata sullo stesso oggetto (di nuovo: i
    rerun di Streamlit) leggerebbe da EOF e vedrebbe un file vuoto.

    Restituisce (file_testo, va_chiuso).
    """
    if isinstance(file_like, str):
        return open(file_like, "r", encoding="utf-8-sig", newline=""), True

    if hasattr(file_like, "seek") and getattr(file_like, "seekable", lambda: True)():
        file_like.seek(0)

    contenuto = file_like.read()
    if isinstance(contenuto, bytes):
        contenuto = contenuto.decode("utf-8-sig")
    else:
        # Un file-like testuale aperto senza utf-8-sig può conservare il BOM
        # come primo carattere: lo togliamo per non ritrovarlo nel nome della
        # prima colonna dell'intestazione.
        contenuto = contenuto.lstrip("\ufeff")

    return io.StringIO(contenuto, newline=""), True


def parse_esercizi_csv(file_like) -> list[dict]:
    """
    Legge un CSV di esercizi (file-like o percorso) e restituisce una lista
    di dizionari con le chiavi delle 5 colonne obbligatorie (nome,
    spiegazione, note, ripetizioni, recupero) più le chiavi opzionali del
    manifest, sempre presenti: gruppo (str, default ""), video_url (str,
    default ""), ts_start / ts_finish (float o None), frame_start /
    frame_finish (str o None).

    Accetta un percorso stringa, un file-like testuale o un file-like
    binario (es. io.BytesIO, come usato da scheda_file per leggere il
    manifest direttamente dallo zip del bundle .scheda).

    Solleva ValueError con un messaggio chiaro se le colonne obbligatorie non
    sono tutte presenti nel file, oppure se un timestamp non è numerico.
    """
    file_testo, va_chiuso = _apri_testo(file_like)
    try:
        lettore = csv.DictReader(file_testo)
        colonne_presenti = set(lettore.fieldnames or [])
        colonne_mancanti = COLONNE_ATTESE - colonne_presenti
        if colonne_mancanti:
            raise ValueError(
                "Il file CSV non contiene le colonne richieste. "
                f"Colonne mancanti: {sorted(colonne_mancanti)}. "
                f"Colonne attese: {sorted(COLONNE_ATTESE)}."
            )

        esercizi = []
        for riga in lettore:
            esercizio = {
                "nome": (riga.get("Nome") or "").strip(),
                "spiegazione": (riga.get("Spiegazione") or "").strip(),
                "note": (riga.get("Note") or "").strip(),
                "ripetizioni": (riga.get("Ripetizioni") or "").strip(),
                "recupero": (riga.get("Recupero") or "").strip(),
                "gruppo": (riga.get("Gruppo") or "").strip() if "Gruppo" in colonne_presenti else "",
                "video_url": (
                    (riga.get("VideoURL") or "").strip() if "VideoURL" in colonne_presenti else ""
                ),
                "ts_start": (
                    _timestamp_o_none(riga.get("TimestampStart"), "TimestampStart")
                    if "TimestampStart" in colonne_presenti
                    else None
                ),
                "ts_finish": (
                    _timestamp_o_none(riga.get("TimestampFinish"), "TimestampFinish")
                    if "TimestampFinish" in colonne_presenti
                    else None
                ),
                "frame_start": (
                    ((riga.get("FrameStartPath") or "").strip() or None)
                    if "FrameStartPath" in colonne_presenti
                    else None
                ),
                "frame_finish": (
                    ((riga.get("FrameFinishPath") or "").strip() or None)
                    if "FrameFinishPath" in colonne_presenti
                    else None
                ),
            }
            esercizi.append(esercizio)
        return esercizi
    finally:
        if va_chiuso:
            file_testo.close()


def _righe_da_esercizi(esercizi: list[dict]) -> list[dict]:
    """
    Costruisce le righe (dizionari colonna -> valore) delle 11 colonne del
    manifest (le 5 obbligatorie più le 6 opzionali, nell'ordine di
    _COLONNE_CSV_COMPLETE) a partire dalla lista di dizionari esercizio. Le
    chiavi opzionali mancanti o a None diventano celle vuote. Logica
    condivisa da scrivi_esercizi_csv() ed esercizi_csv_bytes(), che
    differiscono solo per la destinazione (file su disco o buffer in
    memoria).
    """
    righe = []
    for esercizio in esercizi:
        righe.append(
            {
                "Nome": esercizio.get("nome", ""),
                "Spiegazione": esercizio.get("spiegazione", ""),
                "Note": esercizio.get("note", ""),
                "Ripetizioni": esercizio.get("ripetizioni", ""),
                "Recupero": esercizio.get("recupero", ""),
                "Gruppo": esercizio.get("gruppo") or "",
                "VideoURL": esercizio.get("video_url") or "",
                "TimestampStart": "" if esercizio.get("ts_start") is None else esercizio["ts_start"],
                "TimestampFinish": "" if esercizio.get("ts_finish") is None else esercizio["ts_finish"],
                "FrameStartPath": esercizio.get("frame_start") or "",
                "FrameFinishPath": esercizio.get("frame_finish") or "",
            }
        )
    return righe


def scrivi_esercizi_csv(esercizi: list[dict], percorso: str) -> None:
    """
    Riscrive il CSV arricchito con tutte le 11 colonne (le 5 obbligatorie più
    le 6 opzionali del manifest, nell'ordine di _COLONNE_CSV_COMPLETE). È il
    "salvataggio" della scheda: un successivo parse_esercizi_csv(percorso)
    restituisce gli stessi valori (round-trip). Le chiavi opzionali mancanti
    o a None diventano celle vuote nel CSV.
    """
    righe = _righe_da_esercizi(esercizi)
    with open(percorso, "w", encoding="utf-8", newline="") as file_csv:
        scrittore = csv.DictWriter(file_csv, fieldnames=_COLONNE_CSV_COMPLETE, lineterminator="\n")
        scrittore.writeheader()
        scrittore.writerows(righe)


def esercizi_csv_bytes(esercizi: list[dict]) -> bytes:
    """
    Genera in memoria (nessun file su disco) lo stesso CSV arricchito
    prodotto da scrivi_esercizi_csv(), utile per il bottone di download
    diretto dall'interfaccia Streamlit. Riusa _righe_da_esercizi() per non
    duplicare la logica di costruzione delle colonne.
    """
    righe = _righe_da_esercizi(esercizi)
    buffer = io.StringIO(newline="")
    scrittore = csv.DictWriter(buffer, fieldnames=_COLONNE_CSV_COMPLETE, lineterminator="\n")
    scrittore.writeheader()
    scrittore.writerows(righe)
    return buffer.getvalue().encode("utf-8")
