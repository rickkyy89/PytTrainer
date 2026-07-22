"""
Funzioni pure per il parsing/validazione del CSV degli esercizi, riusate sia
da app.py che dai test (nessuna dipendenza da Streamlit).

Il CSV funge da manifest persistente della scheda: oltre alle 5 colonne
obbligatorie supporta colonne opzionali (COLONNE_OPZIONALI) che tracciano la
scelta di video, timestamp e frame estratti per ciascun esercizio. Se le
colonne opzionali sono assenti (o vuote), il comportamento resta identico a
quello di un CSV "minimo": ricerca automatica del video ed euristica sui
timestamp.
"""

from __future__ import annotations

import io
import re

import pandas as pd

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
    if valore is None or (isinstance(valore, float) and pd.isna(valore)):
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


def parse_esercizi_csv(file_like) -> list[dict]:
    """
    Legge un CSV di esercizi (file-like o percorso) e restituisce una lista
    di dizionari con le chiavi delle 5 colonne obbligatorie (nome,
    spiegazione, note, ripetizioni, recupero) più le chiavi opzionali del
    manifest, sempre presenti: gruppo (str, default ""), video_url (str,
    default ""), ts_start / ts_finish (float o None), frame_start /
    frame_finish (str o None).

    Solleva ValueError con un messaggio chiaro se le colonne obbligatorie non
    sono tutte presenti nel file, oppure se un timestamp non è numerico.
    """
    df = pd.read_csv(file_like)

    colonne_presenti = set(df.columns)
    colonne_mancanti = COLONNE_ATTESE - colonne_presenti
    if colonne_mancanti:
        raise ValueError(
            "Il file CSV non contiene le colonne richieste. "
            f"Colonne mancanti: {sorted(colonne_mancanti)}. "
            f"Colonne attese: {sorted(COLONNE_ATTESE)}."
        )

    # I valori mancanti (NaN) diventano stringhe vuote per evitare problemi a
    # valle (rendering UI, generazione documento). I timestamp sono esclusi
    # da questo riempimento perché gestiti a parte (serve distinguere
    # "assente" da un eventuale "0").
    colonne_timestamp = {"TimestampStart", "TimestampFinish"}
    colonne_da_riempire = [colonna for colonna in df.columns if colonna not in colonne_timestamp]
    df[colonne_da_riempire] = df[colonne_da_riempire].fillna("")

    esercizi = []
    for _, riga in df.iterrows():
        esercizio = {
            "nome": str(riga["Nome"]).strip(),
            "spiegazione": str(riga["Spiegazione"]).strip(),
            "note": str(riga["Note"]).strip(),
            "ripetizioni": str(riga["Ripetizioni"]).strip(),
            "recupero": str(riga["Recupero"]).strip(),
            "gruppo": str(riga["Gruppo"]).strip() if "Gruppo" in df.columns else "",
            "video_url": str(riga["VideoURL"]).strip() if "VideoURL" in df.columns else "",
            "ts_start": (
                _timestamp_o_none(riga["TimestampStart"], "TimestampStart")
                if "TimestampStart" in df.columns
                else None
            ),
            "ts_finish": (
                _timestamp_o_none(riga["TimestampFinish"], "TimestampFinish")
                if "TimestampFinish" in df.columns
                else None
            ),
            "frame_start": (
                (str(riga["FrameStartPath"]).strip() or None) if "FrameStartPath" in df.columns else None
            ),
            "frame_finish": (
                (str(riga["FrameFinishPath"]).strip() or None) if "FrameFinishPath" in df.columns else None
            ),
        }
        esercizi.append(esercizio)
    return esercizi


def _dataframe_da_esercizi(esercizi: list[dict]) -> pd.DataFrame:
    """
    Costruisce il DataFrame delle 11 colonne del manifest (le 5 obbligatorie
    più le 6 opzionali, nell'ordine di _COLONNE_CSV_COMPLETE) a partire dalla
    lista di dizionari esercizio. Le chiavi opzionali mancanti o a None
    diventano celle vuote. Logica condivisa da scrivi_esercizi_csv() ed
    esercizi_csv_bytes(), che differiscono solo per la destinazione (file su
    disco o buffer in memoria).
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
    return pd.DataFrame(righe, columns=_COLONNE_CSV_COMPLETE)


def scrivi_esercizi_csv(esercizi: list[dict], percorso: str) -> None:
    """
    Riscrive il CSV arricchito con tutte le 11 colonne (le 5 obbligatorie più
    le 6 opzionali del manifest, nell'ordine di _COLONNE_CSV_COMPLETE). È il
    "salvataggio" della scheda: un successivo parse_esercizi_csv(percorso)
    restituisce gli stessi valori (round-trip). Le chiavi opzionali mancanti
    o a None diventano celle vuote nel CSV.
    """
    df = _dataframe_da_esercizi(esercizi)
    df.to_csv(percorso, index=False)


def esercizi_csv_bytes(esercizi: list[dict]) -> bytes:
    """
    Genera in memoria (nessun file su disco) lo stesso CSV arricchito
    prodotto da scrivi_esercizi_csv(), utile per il bottone di download
    diretto dall'interfaccia Streamlit. Riusa _dataframe_da_esercizi() per
    non duplicare la logica di costruzione delle colonne.
    """
    df = _dataframe_da_esercizi(esercizi)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")
