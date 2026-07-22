"""
Funzioni pure per il parsing/validazione del CSV degli esercizi, riusate sia
da app.py che dai test (nessuna dipendenza da Streamlit).
"""

from __future__ import annotations

import pandas as pd

COLONNE_ATTESE = {"Nome", "Spiegazione", "Note", "Ripetizioni", "Recupero"}


def parse_esercizi_csv(file_like) -> list[dict]:
    """
    Legge un CSV di esercizi (file-like o percorso) e restituisce una lista
    di dizionari con chiavi in minuscolo (nome, spiegazione, note,
    ripetizioni, recupero), pronti per essere aggiunti alla lista esercizi.

    Solleva ValueError con un messaggio chiaro se le colonne attese non sono
    tutte presenti nel file.
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

    # I valori mancanti (NaN) diventano stringhe vuote per evitare problemi
    # a valle (rendering UI, generazione documento).
    df = df.fillna("")

    esercizi = []
    for _, riga in df.iterrows():
        esercizi.append(
            {
                "nome": str(riga["Nome"]).strip(),
                "spiegazione": str(riga["Spiegazione"]).strip(),
                "note": str(riga["Note"]).strip(),
                "ripetizioni": str(riga["Ripetizioni"]).strip(),
                "recupero": str(riga["Recupero"]).strip(),
            }
        )
    return esercizi
