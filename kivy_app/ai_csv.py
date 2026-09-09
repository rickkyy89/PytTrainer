"""CSV di esempio e prompt template per generare una scheda con un'AI esterna.

Nessun Kivy e nessun Android qui: la UI copia :data:`PROMPT_TEMPLATE` negli
appunti e il controller salva :func:`csv_esempio` nella cartella Download.
Il testo d'esempio dentro il prompt e il file CSV salvato derivano dalle
stesse righe, cosi l'AI vede esattamente il formato che il parser accetta.
"""

from __future__ import annotations

import csv
import io

NOME_CSV_ESEMPIO = "esempio_scheda_ai.csv"

# Colonne che il prompt chiede all'AI: le 5 obbligatorie del parser piu
# Gruppo (sezione della scheda). Le altre opzionali non vengono menzionate.
COLONNE_ESEMPIO = ["Nome", "Spiegazione", "Note", "Ripetizioni", "Recupero", "Gruppo"]

ESEMPI_ESERCIZI = [
    {
        "Nome": "Marcia sul posto",
        "Spiegazione": "Alza le ginocchia a vita bassa alternando le braccia, "
                       "ritmo vivace. Mantieni il busto eretto e appoggia da prima l'avampiede.",
        "Note": "Respira in modo regolare, non inarcare la schiena.",
        "Ripetizioni": "2 MIN",
        "Recupero": "0 SEC",
        "Gruppo": "Riscaldamento",
    },
    {
        "Nome": "Squat al corpo libero",
        "Spiegazione": "Piedi larghezza spalle, scendi flettendo anche e ginocchia "
                       "come se ti sedessi, poi risali spingendo sui talloni.",
        "Note": "Le ginocchia restano in linea coi piedi, schiena neutra.",
        "Ripetizioni": "3x12",
        "Recupero": "90 SEC",
        "Gruppo": "Forza",
    },
    {
        "Nome": "Push-up sulle ginocchia",
        "Spiegazione": "Mani sotto le spalle, corpo dritto dalle ginocchia alla testa. "
                       "Scendi toccando quasi il pavimento e risali spingendo da terra.",
        "Note": "Non lasciare cadere il bacino: addominali contratti.",
        "Ripetizioni": "3x10",
        "Recupero": "60 SEC",
        "Gruppo": "Forza",
    },
]


def csv_esempio() -> str:
    """Il CSV di esempio cosi come viene salvato in Download (e mostrato nel prompt)."""
    buffer = io.StringIO(newline="")
    scrittore = csv.DictWriter(buffer, fieldnames=COLONNE_ESEMPIO, lineterminator="\n")
    scrittore.writeheader()
    scrittore.writerows(ESEMPI_ESERCIZI)
    return buffer.getvalue()


PROMPT_TEMPLATE = f"""Sei un personal trainer e devi generare il file .csv che l'app pyTrainer usa per creare una scheda di allenamento A4 con i video degli esercizi. Rispondi SOLO con il CSV: niente titolo, niente spiegazioni, niente blockquote o ```.

FORMATO (obbligatorio, il file viene parsato cosi com'e)
- La riga 1 e esattamente questo titolo:
  {",".join(COLONNE_ESEMPIO)}
- Ogni riga successiva e un esercizio, con gli stessi 6 campi nello stesso ordine.
- Codifica UTF-8, nessun campo vuoto nella colonna Nome, nessuna riga vuota o di commento.
- Un campo che contiene virgole, virgolette o a capo va racchiuso tra doppi apici, raddoppiando gli apici interni.

COLONNE
- Nome: nome dell'esercizio in italiano (es. Squat con bilanciere).
- Spiegazione: come si esegue, 2-3 frasi tecniche (partenza, movimento, ritorno).
- Note: 1-2 frasi con errori da evitare o consigli di sicurezza.
- Ripetizioni: serie x ripetizioni (3x12, 4x8, 3x10 per gamba) o durata tipo 30 SEC / 2 MIN per gli esercizi a tempo.
- Recupero: pausa tra le serie, sempre numero + spazio + SEC oppure MIN (es. 90 SEC).
- Gruppo: sezione della scheda (es. Riscaldamento, Attivazione, Forza, Cardio, Defaticamento). Esercizi dello stesso Gruppo vanno in righe consecutive e le righe seguono l'ordine reale della sessione.

I video non servono: pyTrainer cerca da solo i tutorial su YouTube per ogni esercizio, quindi non aggiungere colonne extra come VideoURL o timestamp.

Ecco un esempio di file corretto:
{csv_esempio().rstrip()}

Ora genera il CSV della scheda che ti chiede l'utente qui sotto (livello, distretti, attrezzi disponibili, durata, numero di esercizi). Se la richiesta non specifica qualcosa, scegli tu l'opzione piu sensata e produci comunque il file completo:
>>> DESCRIVI QUI LA TUA SCHEDA, poi incolla tutto in Gemini/ChatGPT e salva il CSV che ti viene dato <<<"""
