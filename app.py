"""
Workout Sheet Automator - app Streamlit locale per creare schede di
allenamento A4 su Google Docs a partire da una lista di esercizi, con
ricerca video YouTube e estrazione automatica dei frame START/FINISH.
"""

import os
import shutil

import streamlit as st

from csv_utils import COLONNE_ATTESE, parse_esercizi_csv
from google_docs_helper import GoogleAuthError, GoogleDocsError, create_workout_document
from video_helper import (
    FrameExtractionError,
    VideoSearchError,
    extract_start_finish_frames,
    search_youtube,
)

PERCORSO_CSV_ESEMPIO = "esercizi_example.csv"


def _nuovo_esercizio(nome="", spiegazione="", note="", ripetizioni="", recupero=""):
    """Crea un dizionario esercizio con tutte le chiavi usate dall'app inizializzate."""
    return {
        "nome": nome,
        "spiegazione": spiegazione,
        "note": note,
        "ripetizioni": ripetizioni,
        "recupero": recupero,
        "video_url": "",
        "risultati_ricerca": [],
        "frame_start": None,
        "frame_finish": None,
        "ts_start": 0.0,
        "ts_finish": 1.0,
    }


def _formatta_durata(secondi):
    """Formatta una durata in secondi come mm:ss, gestendo valori mancanti."""
    if not secondi:
        return "durata sconosciuta"
    secondi = int(secondi)
    minuti = secondi // 60
    resto = secondi % 60
    return f"{minuti:02d}:{resto:02d}"


def main():
    st.set_page_config(page_title="Workout Sheet Automator", layout="wide", page_icon="🏋️")

    if "esercizi" not in st.session_state:
        st.session_state["esercizi"] = []

    # --- Sidebar ---------------------------------------------------------
    with st.sidebar:
        st.title("🏋️ Workout Sheet Automator")
        titolo_scheda = st.text_input(
            "Titolo scheda", value="SCHEDA 1: GAMBE & GLUTEI", key="titolo_scheda"
        )

        st.markdown("---")
        st.subheader("Credenziali Google")
        credenziali_presenti = any(
            os.path.exists(percorso)
            for percorso in ("credentials.json", "service_account.json", "token.json")
        )
        if credenziali_presenti:
            st.success("Credenziali Google trovate.")
        else:
            st.warning(
                "Nessuna credenziale Google trovata. Per generare il documento serve "
                "'credentials.json' (OAuth) oppure 'service_account.json' nella cartella "
                "principale del progetto. Consulta il README per le istruzioni complete."
            )

        st.markdown("---")
        if st.button("🗑️ Svuota lista esercizi"):
            st.session_state["esercizi"] = []
            st.rerun()

    if shutil.which("ffmpeg") is None:
        st.warning(
            "⚠️ ffmpeg non risulta installato o non è nel PATH. L'estrazione dei frame "
            "START/FINISH non funzionerà finché non lo installi (vedi README)."
        )

    st.header("Esercizi della scheda")

    # --- Tab di inserimento -----------------------------------------------
    tab_manuale, tab_csv = st.tabs(["➕ Inserimento manuale", "📄 Carica CSV"])

    with tab_manuale:
        with st.form("form_inserimento_manuale", clear_on_submit=True):
            nome = st.text_input("Nome esercizio")
            spiegazione = st.text_area("Spiegazione")
            note = st.text_area("Note")
            colonna_rip, colonna_rec = st.columns(2)
            with colonna_rip:
                ripetizioni = st.text_input("Ripetizioni (es. 3x12)")
            with colonna_rec:
                recupero = st.text_input("Recupero (es. 90 SEC)")
            inviato = st.form_submit_button("Aggiungi esercizio")

        if inviato:
            if nome.strip():
                st.session_state["esercizi"].append(
                    _nuovo_esercizio(nome.strip(), spiegazione, note, ripetizioni, recupero)
                )
                st.rerun()
            else:
                st.warning("Il nome dell'esercizio è obbligatorio.")

    with tab_csv:
        st.write(f"Colonne richieste nel file CSV: {', '.join(sorted(COLONNE_ATTESE))}")

        if os.path.exists(PERCORSO_CSV_ESEMPIO):
            with open(PERCORSO_CSV_ESEMPIO, "rb") as file_esempio:
                st.download_button(
                    "⬇️ Scarica CSV di esempio",
                    data=file_esempio.read(),
                    file_name="esercizi_example.csv",
                    mime="text/csv",
                )

        file_caricato = st.file_uploader("Carica file CSV", type=["csv"], key="csv_uploader")
        if file_caricato is not None:
            try:
                esercizi_importati = parse_esercizi_csv(file_caricato)
            except ValueError as errore:
                st.error(str(errore))
            except Exception as errore:  # errori generici di parsing pandas
                st.error(f"Errore durante la lettura del CSV: {errore}")
            else:
                st.success(f"Trovati {len(esercizi_importati)} esercizi nel file.")
                st.dataframe(esercizi_importati, use_container_width=True)
                if st.button("➕ Importa esercizi nella lista"):
                    for riga in esercizi_importati:
                        st.session_state["esercizi"].append(
                            _nuovo_esercizio(
                                riga["nome"],
                                riga["spiegazione"],
                                riga["note"],
                                riga["ripetizioni"],
                                riga["recupero"],
                            )
                        )
                    st.rerun()

    st.markdown("---")

    # --- Elenco esercizi con gestione video/frame -------------------------
    indice_da_rimuovere = None

    for i, esercizio in enumerate(st.session_state["esercizi"]):
        etichetta = esercizio["nome"] or f"Esercizio {i + 1}"
        with st.expander(f"{i + 1}. {etichetta}", expanded=False):

            st.subheader("Ricerca video YouTube")
            if st.button("🔍 Cerca su YouTube", key=f"cerca_{i}"):
                if esercizio["nome"].strip():
                    try:
                        with st.spinner("Ricerca dei video in corso..."):
                            risultati = search_youtube(esercizio["nome"])
                        st.session_state["esercizi"][i]["risultati_ricerca"] = risultati
                        if not risultati:
                            st.info("Nessun video trovato per questo esercizio.")
                    except VideoSearchError as errore:
                        st.error(str(errore))
                else:
                    st.warning("Inserisci prima un nome per l'esercizio.")

            risultati_ricerca = esercizio.get("risultati_ricerca") or []
            video_selezionato_url = None

            if risultati_ricerca:
                risultati_mostrati = risultati_ricerca[:3]
                colonne_video = st.columns(len(risultati_mostrati))
                for idx, video in enumerate(risultati_mostrati):
                    with colonne_video[idx]:
                        st.image(video["thumbnail"], use_container_width=True)
                        st.caption(video["title"])
                        st.text(_formatta_durata(video.get("duration")))
                        st.video(video["webpage_url"])

                etichette_radio = [v["title"] for v in risultati_mostrati]
                scelta = st.radio(
                    "Seleziona il video da usare",
                    options=range(len(risultati_mostrati)),
                    format_func=lambda x: etichette_radio[x],
                    key=f"radio_video_{i}",
                )
                video_selezionato_url = risultati_mostrati[scelta]["webpage_url"]

            url_manuale = st.text_input(
                "Oppure incolla un URL YouTube diretto",
                value=esercizio.get("video_url") or "",
                key=f"url_manuale_{i}",
            )

            # L'URL incollato manualmente ha sempre precedenza sulla selezione da ricerca.
            if url_manuale.strip():
                video_url_finale = url_manuale.strip()
            elif video_selezionato_url:
                video_url_finale = video_selezionato_url
            else:
                video_url_finale = ""
            st.session_state["esercizi"][i]["video_url"] = video_url_finale

            st.subheader("Timestamp ed estrazione frame")
            colonna_start, colonna_finish = st.columns(2)
            with colonna_start:
                ts_start = st.number_input(
                    "Timestamp START (sec)",
                    min_value=0.0,
                    step=0.5,
                    value=float(esercizio.get("ts_start") or 0.0),
                    key=f"ts_start_{i}",
                )
            with colonna_finish:
                ts_finish = st.number_input(
                    "Timestamp FINISH (sec)",
                    min_value=0.0,
                    step=0.5,
                    value=float(esercizio.get("ts_finish") or 1.0),
                    key=f"ts_finish_{i}",
                )
            st.session_state["esercizi"][i]["ts_start"] = ts_start
            st.session_state["esercizi"][i]["ts_finish"] = ts_finish

            timestamp_validi = ts_finish > ts_start
            if not timestamp_validi:
                st.warning("Il timestamp FINISH deve essere maggiore del timestamp START.")

            if st.button("🎬 Estrai frame", key=f"estrai_{i}"):
                if not video_url_finale:
                    st.error("Seleziona un video dai risultati di ricerca oppure incolla un URL.")
                elif not timestamp_validi:
                    st.error("Correggi i timestamp prima di estrarre i frame.")
                else:
                    try:
                        with st.spinner("Estrazione dei frame in corso (può richiedere qualche secondo)..."):
                            percorso_start, percorso_finish = extract_start_finish_frames(
                                video_url_finale,
                                ts_start,
                                ts_finish,
                                esercizio["nome"] or f"esercizio_{i + 1}",
                            )
                        st.session_state["esercizi"][i]["frame_start"] = percorso_start
                        st.session_state["esercizi"][i]["frame_finish"] = percorso_finish
                        st.success("Frame estratti con successo.")
                    except (VideoSearchError, FrameExtractionError) as errore:
                        st.error(str(errore))
                    except Exception as errore:
                        st.error(f"Errore imprevisto durante l'estrazione dei frame: {errore}")

            frame_start = st.session_state["esercizi"][i].get("frame_start")
            frame_finish = st.session_state["esercizi"][i].get("frame_finish")
            if frame_start and frame_finish and os.path.exists(frame_start) and os.path.exists(frame_finish):
                colonna_img_start, colonna_img_finish = st.columns(2)
                with colonna_img_start:
                    st.image(frame_start, caption="START")
                with colonna_img_finish:
                    st.image(frame_finish, caption="FINISH")

            st.subheader("Dettagli esercizio")
            nome_modificato = st.text_input("Nome esercizio", value=esercizio["nome"], key=f"nome_{i}")
            spiegazione_modificata = st.text_area(
                "Spiegazione", value=esercizio["spiegazione"], key=f"spiegazione_{i}"
            )
            note_modificate = st.text_area("Note", value=esercizio["note"], key=f"note_{i}")
            colonna_rip_edit, colonna_rec_edit = st.columns(2)
            with colonna_rip_edit:
                ripetizioni_modificate = st.text_input(
                    "Ripetizioni", value=esercizio["ripetizioni"], key=f"ripetizioni_{i}"
                )
            with colonna_rec_edit:
                recupero_modificato = st.text_input(
                    "Recupero", value=esercizio["recupero"], key=f"recupero_{i}"
                )

            st.session_state["esercizi"][i].update(
                {
                    "nome": nome_modificato,
                    "spiegazione": spiegazione_modificata,
                    "note": note_modificate,
                    "ripetizioni": ripetizioni_modificate,
                    "recupero": recupero_modificato,
                }
            )

            if st.button("🗑️ Rimuovi esercizio", key=f"rimuovi_{i}"):
                indice_da_rimuovere = i

    if indice_da_rimuovere is not None:
        del st.session_state["esercizi"][indice_da_rimuovere]
        st.rerun()

    # --- Riepilogo e generazione documento --------------------------------
    st.markdown("---")
    st.header("Generazione documento")

    esercizi_pronti = [
        esercizio
        for esercizio in st.session_state["esercizi"]
        if esercizio.get("frame_start") and esercizio.get("frame_finish")
    ]
    totale_esercizi = len(st.session_state["esercizi"])
    st.write(
        f"**Esercizi pronti (con frame START e FINISH estratti):** "
        f"{len(esercizi_pronti)} / {totale_esercizi}"
    )

    genera_disabilitato = len(esercizi_pronti) == 0
    if st.button("📄 Genera Google Doc", type="primary", disabled=genera_disabilitato):
        try:
            with st.spinner("Generazione del documento su Google Docs in corso..."):
                risultato = create_workout_document(esercizi_pronti, titolo_scheda)
            st.success(f"Documento generato con successo! [Apri il documento]({risultato['url']})")
        except GoogleAuthError as errore:
            st.error(str(errore))
        except GoogleDocsError as errore:
            st.error(str(errore))
        except Exception as errore:
            st.error(f"Errore imprevisto durante la generazione del documento: {errore}")


if __name__ == "__main__":
    main()
