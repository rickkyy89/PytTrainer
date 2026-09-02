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

import csv
import io
import math
import os
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


def slugs_unici(esercizi: list[dict]) -> list[str]:
    """
    Restituisce uno slug unico per ogni esercizio, mantenendo l'ordine.
    Duplicati ottengono suffisso _2, _3 ... (es. squat, squat_2). La
    generazione è deterministica e gestisce anche collisioni con slug già
    presenti come "squat_2" naturale.
    """
    contatori: dict[str, int] = {}
    visti: set[str] = set()
    risultato: list[str] = []
    for esercizio in esercizi:
        base = slugify(str(esercizio.get("nome") or "esercizio"))
        # Se il base non è mai stato usato e non collide con un suffisso già emesso
        if base not in visti and base not in contatori:
            slug = base
            contatori[base] = 1
        else:
            # Serve un suffisso numerico
            n = contatori.get(base, 1) + 1
            # Cerca il primo libero
            while True:
                candidato = f"{base}_{n}"
                if candidato not in visti:
                    slug = candidato
                    contatori[base] = n
                    break
                n += 1
        visti.add(slug)
        risultato.append(slug)
    return risultato


def trova_duplicati_slug(esercizi: list[dict]) -> dict[str, list[int]]:
    """
    Mappa slug base -> indici degli esercizi che lo condividono (solo gruppi >1).
    Utile per mostrare un avviso in UI.
    """
    mappa: dict[str, list[int]] = {}
    for idx, esercizio in enumerate(esercizi):
        slug = slugify(str(esercizio.get("nome") or "esercizio"))
        mappa.setdefault(slug, []).append(idx)
    return {slug: indici for slug, indici in mappa.items() if len(indici) > 1}


def _timestamp_o_none(valore, nome_colonna: str) -> float | None:
    """
    Converte una cella di timestamp in float, oppure None se la cella è
    vuota/assente. Solleva ValueError con messaggio chiaro se il valore non è
    numerico.
    """
    if valore is None or (isinstance(valore, float) and math.isnan(valore)):
        return None
    testo = str(valore).strip()
    if not testo or testo.casefold() in {
        "#n/a",
        "#na",
        "-nan",
        "-1.#ind",
        "-1.#qnan",
        "-na",
        "1.#ind",
        "1.#qnan",
        "<na>",
        "n/a",
        "na",
        "nan",
        "null",
        "none",
    }:
        return None
    try:
        timestamp = float(testo)
    except ValueError as exc:
        raise ValueError(
            f"Valore non numerico nella colonna '{nome_colonna}': '{testo}'. "
            "I timestamp devono essere numeri (secondi), es. 12.5."
        ) from exc
    return None if math.isnan(timestamp) else timestamp


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
    testo = _leggi_testo_csv(file_like)
    lettore = csv.DictReader(io.StringIO(testo))
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
            "nome": _testo_cella(riga["Nome"]),
            "spiegazione": _testo_cella(riga["Spiegazione"]),
            "note": _testo_cella(riga["Note"]),
            "ripetizioni": _testo_cella(riga["Ripetizioni"]),
            "recupero": _testo_cella(riga["Recupero"]),
            "gruppo": _testo_cella(riga["Gruppo"]) if "Gruppo" in colonne_presenti else "",
            "video_url": _testo_cella(riga["VideoURL"]) if "VideoURL" in colonne_presenti else "",
            "ts_start": (
                _timestamp_o_none(riga["TimestampStart"], "TimestampStart")
                if "TimestampStart" in colonne_presenti
                else None
            ),
            "ts_finish": (
                _timestamp_o_none(riga["TimestampFinish"], "TimestampFinish")
                if "TimestampFinish" in colonne_presenti
                else None
            ),
            "frame_start": (
                (_testo_cella(riga["FrameStartPath"]) or None)
                if "FrameStartPath" in colonne_presenti
                else None
            ),
            "frame_finish": (
                (_testo_cella(riga["FrameFinishPath"]) or None)
                if "FrameFinishPath" in colonne_presenti
                else None
            ),
        }
        esercizi.append(esercizio)
    return esercizi


def _leggi_testo_csv(file_like) -> str:
    """Restituisce testo UTF-8 da un percorso o da un file-like testuale/binario."""
    if isinstance(file_like, (str, bytes, os.PathLike)):
        with open(file_like, encoding="utf-8-sig", newline="") as file_csv:
            return file_csv.read()

    contenuto = file_like.read()
    if isinstance(contenuto, bytes):
        return contenuto.decode("utf-8-sig")
    return contenuto


def _testo_cella(valore) -> str:
    return "" if valore is None else str(valore).strip()


def _righe_csv_da_esercizi(esercizi: list[dict]) -> list[dict]:
    """
    Costruisce le righe delle 11 colonne del manifest (le 5 obbligatorie
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
    return righe


def _csv_testo_da_esercizi(esercizi: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    scrittore = csv.DictWriter(buffer, fieldnames=_COLONNE_CSV_COMPLETE, lineterminator="\n")
    scrittore.writeheader()
    scrittore.writerows(_righe_csv_da_esercizi(esercizi))
    return buffer.getvalue()


def scrivi_esercizi_csv(esercizi: list[dict], percorso: str) -> None:
    """
    Riscrive il CSV arricchito con tutte le 11 colonne (le 5 obbligatorie più
    le 6 opzionali del manifest, nell'ordine di _COLONNE_CSV_COMPLETE). È il
    "salvataggio" della scheda: un successivo parse_esercizi_csv(percorso)
    restituisce gli stessi valori (round-trip). Le chiavi opzionali mancanti
    o a None diventano celle vuote nel CSV.
    """
    with open(percorso, "w", encoding="utf-8", newline="") as file_csv:
        file_csv.write(_csv_testo_da_esercizi(esercizi))


def esercizi_csv_bytes(esercizi: list[dict]) -> bytes:
    """
    Genera in memoria (nessun file su disco) lo stesso CSV arricchito
    prodotto da scrivi_esercizi_csv(), utile per il bottone di download
    diretto dall'interfaccia Streamlit. Riusa _righe_csv_da_esercizi() per
    non duplicare la logica di costruzione delle colonne.
    """
    return _csv_testo_da_esercizi(esercizi).encode("utf-8")
