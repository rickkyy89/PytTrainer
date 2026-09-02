"""
Workout Sheet Automator - app Streamlit locale per creare schede di
allenamento A4 su Google Docs a partire da una lista di esercizi, con
ricerca video YouTube e estrazione automatica dei frame START/FINISH.
"""

import json
import os
import shutil
import uuid
from pathlib import Path

import streamlit as st
from PIL import Image

from core.csv_utils import parse_esercizi_csv, trova_duplicati_slug
from core.docs_helper import GoogleAuthError, GoogleDocsError, create_workout_document
from core.platform import LocalCredentialsProvider
from core.scheda_file import (
    SchedaFileError,
    carica_scheda,
    cartella_frames,
    cartella_lavoro_per_bundle,
    percorso_stato,
    salva_scheda,
    titolo_scheda as titolo_scheda_salvato,
)
from core.video_helper import (
    FrameExtractionError,
    VideoSearchError,
    box_ritaglio,
    crop_frame,
    extract_start_finish_frames,
    importa_frame_da_immagine,
    search_youtube,
)

# Cartella Google Drive dove finiscono tutti i workout esportati.
URL_CARTELLA_DRIVE = "https://drive.google.com/drive/folders/1UthYZdR1GiVADYNUWBN1cX3z790FEkXq"
APP_BASE_DIR = Path(__file__).resolve().parent
GOOGLE_CREDENTIALS = LocalCredentialsProvider(APP_BASE_DIR)


def _url_doc_corrente():
    """
    URL diretto del Google Doc associato alla scheda corrente, letto dallo
    state.json nella cartella di lavoro (presente nel bundle .scheda se
    l'allenamento è già stato esportato). Ritorna None se non c'è un doc.
    """
    cartella = st.session_state.get("cartella_lavoro")
    if not cartella:
        return None
    percorso = os.path.join(cartella, "state.json")
    if not os.path.exists(percorso):
        return None
    try:
        with open(percorso, encoding="utf-8") as file_stato:
            stato = json.load(file_stato)
    except (OSError, ValueError):
        return None
    doc_id = stato.get("doc_id")
    if not doc_id:
        return None
    return stato.get("url") or f"https://docs.google.com/document/d/{doc_id}/edit"


def _nuovo_esercizio(
    nome="",
    spiegazione="",
    note="",
    ripetizioni="",
    recupero="",
    gruppo="",
    video_url="",
    ts_start=0.0,
    ts_finish=1.0,
    frame_start=None,
    frame_finish=None,
):
    """Crea un dizionario esercizio con tutte le chiavi usate dall'app inizializzate."""
    return {
        "uid": uuid.uuid4().hex[:8],
        "nome": nome,
        "spiegazione": spiegazione,
        "note": note,
        "ripetizioni": ripetizioni,
        "recupero": recupero,
        "gruppo": gruppo,
        "video_url": video_url or "",
        "risultati_ricerca": [],
        "frame_start": frame_start,
        "frame_finish": frame_finish,
        "ts_start": ts_start if ts_start is not None else 0.0,
        "ts_finish": ts_finish if ts_finish is not None else 1.0,
    }


def _esercizio_da_riga(riga):
    """Costruisce un esercizio completo da una riga di manifest (dict con le
    chiavi di parse_esercizi_csv / carica_scheda)."""
    return _nuovo_esercizio(
        riga["nome"],
        riga["spiegazione"],
        riga["note"],
        riga["ripetizioni"],
        riga["recupero"],
        riga.get("gruppo", ""),
        riga.get("video_url", ""),
        riga.get("ts_start"),
        riga.get("ts_finish"),
        riga.get("frame_start"),
        riga.get("frame_finish"),
    )


def _snapshot_esercizi(esercizi, titolo=None):
    """Firma leggera di titolo + lista esercizi per rilevare modifiche non salvate."""
    if titolo is None:
        # Fallback per chiamate legacy senza titolo: usa il titolo in sessione se presente
        try:
            titolo = st.session_state.get("titolo_scheda", "")
        except Exception:
            titolo = ""
    campi = [
        "nome", "spiegazione", "note", "ripetizioni", "recupero", "gruppo",
        "video_url", "ts_start", "ts_finish", "frame_start", "frame_finish",
    ]
    esercizi_firma = [[e.get(c) for c in campi] for e in esercizi]
    return json.dumps([titolo, esercizi_firma], ensure_ascii=False, default=str)


def _formatta_durata(secondi):
    """Formatta una durata in secondi come mm:ss, gestendo valori mancanti."""
    if not secondi:
        return "durata sconosciuta"
    secondi = int(secondi)
    minuti = secondi // 60
    resto = secondi % 60
    return f"{minuti:02d}:{resto:02d}"


def _apri_file_nativo(tipi, titolo="Apri file"):
    """
    Apre un file browser nativo del sistema operativo (tkinter) per scegliere
    un file da aprire. Ritorna il percorso scelto, "" se l'utente annulla, o
    None se il file browser non e' disponibile (es. ambiente headless/server
    senza display). Funziona quando l'app gira in locale sulla macchina.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    try:
        radice = tk.Tk()
        radice.withdraw()
        radice.wm_attributes("-topmost", 1)
        percorso = filedialog.askopenfilename(title=titolo, filetypes=tipi)
        radice.destroy()
    except Exception:
        return None
    return percorso or ""


def _salva_file_nativo(percorso_iniziale="", titolo="Salva scheda"):
    """
    File browser nativo "salva con nome" per un file .scheda. Stessa
    convenzione di ritorno di _apri_file_nativo (percorso, "" se annullato,
    None se non disponibile).
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    try:
        radice = tk.Tk()
        radice.withdraw()
        radice.wm_attributes("-topmost", 1)
        percorso = filedialog.asksaveasfilename(
            title=titolo,
            defaultextension=".scheda",
            filetypes=[("File scheda", "*.scheda"), ("Archivio zip", "*.zip"), ("Tutti i file", "*.*")],
            initialfile=os.path.basename(percorso_iniziale) or "scheda.scheda",
        )
        radice.destroy()
    except Exception:
        return None
    return percorso or ""


def _percorso_backup_frame(percorso_frame):
    """Percorso convenzionale del backup dell'originale non ritagliato di un frame."""
    radice, _ = os.path.splitext(percorso_frame)
    return f"{radice}_orig.jpg"


def _ui_ritaglio_frame(percorso_frame, uid, suffisso):
    """
    Renderizza i controlli di ritaglio (slider percentuali, anteprima live,
    applica/ripristina) per un frame (START o FINISH) di un esercizio. uid e
    suffisso ("start"/"finish") rendono uniche le key dei widget Streamlit.
    """
    colonna_sinistra, colonna_alto, colonna_destra, colonna_basso = st.columns(4)
    with colonna_sinistra:
        sinistra_pct = st.slider("Sinistra %", 0, 45, 0, key=f"crop_sinistra_{suffisso}_{uid}")
    with colonna_alto:
        alto_pct = st.slider("Alto %", 0, 45, 0, key=f"crop_alto_{suffisso}_{uid}")
    with colonna_destra:
        destra_pct = st.slider("Destra %", 0, 45, 0, key=f"crop_destra_{suffisso}_{uid}")
    with colonna_basso:
        basso_pct = st.slider("Basso %", 0, 45, 0, key=f"crop_basso_{suffisso}_{uid}")

    try:
        with Image.open(percorso_frame) as immagine:
            box = box_ritaglio(immagine.size, sinistra_pct, alto_pct, destra_pct, basso_pct)
            st.image(immagine.crop(box), caption="Anteprima ritaglio")
    except (ValueError, OSError) as errore:
        st.error(str(errore))

    percorso_backup = _percorso_backup_frame(percorso_frame)
    colonna_applica, colonna_ripristina = st.columns(2)
    with colonna_applica:
        if st.button("✂️ Applica ritaglio", key=f"applica_crop_{suffisso}_{uid}"):
            try:
                if not os.path.exists(percorso_backup):
                    shutil.copy2(percorso_frame, percorso_backup)
                crop_frame(percorso_frame, sinistra_pct, alto_pct, destra_pct, basso_pct)
            except (ValueError, OSError) as errore:
                st.error(str(errore))
            else:
                st.success("Ritaglio applicato.")
                st.rerun()
    with colonna_ripristina:
        if st.button(
            "↩️ Ripristina originale",
            key=f"ripristina_{suffisso}_{uid}",
            disabled=not os.path.exists(percorso_backup),
        ):
            try:
                shutil.copy2(percorso_backup, percorso_frame)
            except OSError as errore:
                st.error(str(errore))
            else:
                st.success("Originale ripristinato.")
                st.rerun()


def _importa_immagine(indice, suffisso):
    """
    Chiede un'immagine con il file browser nativo e la usa come frame
    START/FINISH dell'esercizio all'indice dato, al posto di quello estratto
    dal video (l'immagine viene convertita in JPEG dentro la cartella frames
    del bundle). Fa il rerun per mostrare subito l'anteprima e il ritaglio.
    """
    percorso = _apri_file_nativo(
        [
            ("Immagini", ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp", "*.gif")),
            ("Tutti i file", "*.*"),
        ],
        f"Scegli l'immagine {suffisso.upper()}",
    )
    if percorso is None:
        st.error("File browser non disponibile. Avvia l'app in locale.")
        return
    if not percorso:
        return

    esercizio = st.session_state["esercizi"][indice]
    try:
        destinazione = importa_frame_da_immagine(
            percorso,
            esercizio["nome"] or f"esercizio_{indice + 1}",
            suffisso,
            output_dir=cartella_frames(st.session_state["cartella_lavoro"]),
        )
    except (FrameExtractionError, ValueError) as errore:
        st.error(str(errore))
    except Exception as errore:
        st.error(f"Errore imprevisto durante l'importazione dell'immagine: {errore}")
    else:
        st.session_state["esercizi"][indice][f"frame_{suffisso}"] = destinazione
        st.rerun()


def _copia_frame_per_inserimento(percorso_src, cartella_lavoro_corrente):
    """Copia un frame (e il suo backup *_orig.jpg) nella cartella frames corrente, con nome unico se collide."""
    if not percorso_src or not os.path.exists(percorso_src):
        return None
    dest_dir = cartella_frames(cartella_lavoro_corrente)
    base = os.path.basename(percorso_src)
    dest = os.path.join(dest_dir, base)
    if os.path.exists(dest):
        # nome già occupato (es. slug duplicato): genera _2, _3 ...
        radice, ext = os.path.splitext(base)
        n = 2
        while True:
            candidato = os.path.join(dest_dir, f"{radice}_{n}{ext}")
            if not os.path.exists(candidato):
                dest = candidato
                break
            n += 1
    try:
        shutil.copy2(percorso_src, dest)
    except OSError:
        return None
    # backup pre-ritaglio, se presente, segue il nome del frame copiato
    backup_src = f"{os.path.splitext(percorso_src)[0]}_orig.jpg"
    if os.path.exists(backup_src):
        backup_dest = f"{os.path.splitext(dest)[0]}_orig.jpg"
        try:
            shutil.copy2(backup_src, backup_dest)
        except OSError:
            pass
    return dest


def _prepara_esercizio_per_inserimento(esercizio, cartella_lavoro_corrente):
    """Ritorna una copia dell'esercizio con uid nuovo e frame copiati nella cartella corrente."""
    nuovo = dict(esercizio)
    nuovo["uid"] = uuid.uuid4().hex[:8]
    nuovo["risultati_ricerca"] = list(esercizio.get("risultati_ricerca") or [])
    for chiave in ("frame_start", "frame_finish"):
        percorso_src = esercizio.get(chiave)
        if percorso_src and os.path.exists(percorso_src):
            copiato = _copia_frame_per_inserimento(percorso_src, cartella_lavoro_corrente)
            nuovo[chiave] = copiato
        else:
            nuovo[chiave] = None
    return nuovo


def _inserisci_esercizi(posizione, nuovi):
    """Inserisce la lista 'nuovi' nella lista esercizi alla 'posizione' data."""
    st.session_state["esercizi"][posizione:posizione] = nuovi


def _lista_riordinata(lista, indici, posizione):
    """
    Ritorna una copia di 'lista' in cui gli elementi agli 'indici' dati sono
    spostati in blocco (mantenendo il loro ordine relativo) in modo che il
    primo finisca alla 'posizione' 1-based richiesta: tutti gli altri scorrono
    di conseguenza, sopra o sotto a seconda della direzione dello spostamento.
    La posizione viene riportata nei limiti validi della lista.
    """
    origine = sorted(set(indici))
    da_spostare = [lista[i] for i in origine]
    resto = [e for i, e in enumerate(lista) if i not in set(origine)]
    destinazione = max(0, min(int(posizione) - 1, len(resto)))
    return resto[:destinazione] + da_spostare + resto[destinazione:]


def _sposta_esercizi(indici, posizione):
    """Sposta gli esercizi agli 'indici' dati alla 'posizione' 1-based richiesta."""
    st.session_state["esercizi"] = _lista_riordinata(
        st.session_state["esercizi"], indici, posizione
    )


def _elimina_esercizi(indici):
    """Rimuove dalla lista gli esercizi agli 'indici' dati."""
    da_rimuovere = set(indici)
    st.session_state["esercizi"] = [
        esercizio
        for i, esercizio in enumerate(st.session_state["esercizi"])
        if i not in da_rimuovere
    ]


def _assicura_uid():
    """
    Garantisce che ogni esercizio in lista abbia un uid: le key dei widget di
    selezione e riordino ci si appoggiano, così restano legate all'esercizio
    anche quando cambia di posizione.
    """
    for esercizio in st.session_state["esercizi"]:
        if not esercizio.get("uid"):
            esercizio["uid"] = uuid.uuid4().hex[:8]


def _chiave_selezione(esercizio):
    """Key della casella di selezione di un esercizio."""
    return f"sel_{esercizio['uid']}"


def _indici_selezionati():
    """Indici degli esercizi con la casella di selezione spuntata."""
    return [
        i
        for i, esercizio in enumerate(st.session_state["esercizi"])
        if st.session_state.get(_chiave_selezione(esercizio))
    ]


def _imposta_selezione(valore):
    """Spunta (o toglie la spunta a) la casella di tutti gli esercizi."""
    for esercizio in st.session_state["esercizi"]:
        st.session_state[_chiave_selezione(esercizio)] = valore


def _numero_posizione(chiave, valore_default, massimo, etichetta="Posizione"):
    """
    Campo numerico 1..massimo per scegliere una posizione di destinazione. Se
    in sessione è rimasto un valore fuori scala (lista accorciata nel
    frattempo) viene riportato nei limiti prima di creare il widget, che
    altrimenti solleverebbe un errore.
    """
    if chiave in st.session_state:
        try:
            st.session_state[chiave] = max(1, min(int(st.session_state[chiave]), massimo))
        except (TypeError, ValueError):
            st.session_state[chiave] = valore_default
        return st.number_input(etichetta, min_value=1, max_value=massimo, step=1, key=chiave)
    return st.number_input(
        etichetta, min_value=1, max_value=massimo, value=valore_default, step=1, key=chiave
    )


def _barra_azioni_multiple():
    """
    Barra delle azioni di gruppo sopra la lista: conta gli esercizi spuntati
    con la casella accanto a ciascuno e permette di spostarli in blocco a una
    posizione o di eliminarli tutti insieme.
    """
    esercizi = st.session_state["esercizi"]
    indici = _indici_selezionati()
    nessuno_selezionato = not indici

    with st.container(border=True):
        colonne = st.columns([3, 2, 2, 2, 3, 3], vertical_alignment="bottom")
        with colonne[0]:
            st.markdown(f"☑️ **{len(indici)}** selezionati su **{len(esercizi)}**")
        with colonne[1]:
            if st.button(
                "Seleziona tutti",
                use_container_width=True,
                disabled=(len(indici) == len(esercizi)),
            ):
                _imposta_selezione(True)
                st.rerun()
        with colonne[2]:
            if st.button("Deseleziona", use_container_width=True, disabled=nessuno_selezionato):
                _imposta_selezione(False)
                st.rerun()
        with colonne[3]:
            posizione = _numero_posizione("pos_multipla", 1, len(esercizi))
        with colonne[4]:
            if st.button(
                "↕️ Sposta selezionati",
                use_container_width=True,
                disabled=nessuno_selezionato,
                help="Sposta gli esercizi spuntati in blocco a partire dalla posizione scelta",
            ):
                _sposta_esercizi(indici, posizione)
                st.rerun()
        with colonne[5]:
            if st.button(
                "🗑️ Elimina selezionati",
                use_container_width=True,
                disabled=nessuno_selezionato,
            ):
                st.session_state["conferma_elimina_selezionati"] = True
                st.rerun()

        if st.session_state.get("conferma_elimina_selezionati"):
            st.warning(f"Eliminare i {len(indici)} esercizi selezionati?")
            colonna_si, colonna_no, _ = st.columns([1, 1, 4])
            with colonna_si:
                if st.button("✅ Sì", key="elimina_selezionati_si", use_container_width=True):
                    _elimina_esercizi(indici)
                    st.session_state["conferma_elimina_selezionati"] = False
                    st.rerun()
            with colonna_no:
                if st.button("❌ No", key="elimina_selezionati_no", use_container_width=True):
                    st.session_state["conferma_elimina_selezionati"] = False
                    st.rerun()


def _blocco_inserimento(posizione, etichetta="➕", aiuto="Inserisci un esercizio qui"):
    """
    Pulsante '+' con popover per inserire esercizi alla 'posizione' data
    (indice nella lista): esercizio manuale, import CSV o import scheda.
    Supporta anche l'inserimento di un singolo esercizio da una scheda esistente,
    utile per comporre una nuova scheda pescando da più schede.
    La posizione rende uniche le key dei widget.
    """
    # Se per questa posizione c'è un import in attesa di scelta, mostra il selettore
    pending = st.session_state.get("pending_single_import")
    if pending and pending.get("posizione") == posizione:
        esercizi_pending = pending.get("esercizi") or []
        sorgente = pending.get("sorgente") or ""
        with st.container(border=True):
            st.markdown(f"**📦 «{os.path.basename(sorgente)}» — {len(esercizi_pending)} esercizi — inserisci in posizione {posizione + 1}:**")
            if not esercizi_pending:
                st.warning("Nessun esercizio trovato nel file selezionato.")
                if st.button("Chiudi", key=f"single_chiudi_vuoto_{posizione}"):
                    st.session_state["pending_single_import"] = None
                    st.rerun()
            else:
                if st.button(f"📦 Inserisci tutta la scheda ({len(esercizi_pending)} esercizi)", key=f"single_all_{posizione}", use_container_width=True):
                    nuovi = [
                        _prepara_esercizio_per_inserimento(ex, st.session_state.get("cartella_lavoro") or "scheda.scheda.work")
                        for ex in esercizi_pending
                    ]
                    _inserisci_esercizi(posizione, nuovi)
                    st.session_state["pending_single_import"] = None
                    st.success(f"Inseriti {len(nuovi)} esercizi in posizione {posizione + 1}.")
                    st.rerun()
                st.markdown("---")
                st.caption("Oppure scegli un singolo esercizio:")
                opzioni = list(range(len(esercizi_pending)))
                etichette = []
                for idx, ex in enumerate(esercizi_pending):
                    nome = (ex.get("nome") or f"Esercizio {idx + 1}").strip()
                    gruppo = (ex.get("gruppo") or "").strip()
                    pref = f"[{gruppo}] " if gruppo else ""
                    etichette.append(f"{idx + 1}. {pref}{nome}")
                scelta = st.selectbox(
                    "Scegli l'esercizio da inserire",
                    options=opzioni,
                    format_func=lambda x: etichette[x],
                    key=f"single_sel_{posizione}",
                )
                scelto = esercizi_pending[scelta]
                st.caption(
                    f"**{scelto.get('nome','')}** — {scelto.get('ripetizioni','')} / {scelto.get('recupero','')} "
                    f"{'— ' + scelto.get('gruppo') if scelto.get('gruppo') else ''}"
                )
                col_ins, col_ann = st.columns(2)
                with col_ins:
                    if st.button("🎯 Inserisci singolo qui", key=f"single_ins_{posizione}", use_container_width=True):
                        nuovo = _prepara_esercizio_per_inserimento(
                            scelto, st.session_state.get("cartella_lavoro") or "scheda.scheda.work"
                        )
                        _inserisci_esercizi(posizione, [nuovo])
                        st.session_state["pending_single_import"] = None
                        st.success(f"Inserito «{scelto.get('nome','')}» in posizione {posizione + 1}.")
                        st.rerun()
                with col_ann:
                    if st.button("❌ Annulla", key=f"single_ann_{posizione}", use_container_width=True):
                        st.session_state["pending_single_import"] = None
                        st.rerun()
    with st.popover(etichetta, help=aiuto):
        st.caption("Inserisci qui:")
        with st.form(f"form_manuale_{posizione}", clear_on_submit=True):
            st.markdown("**➕ Esercizio manuale**")
            nome = st.text_input("Nome esercizio", key=f"add_nome_{posizione}")
            gruppo = st.text_input("Gruppo (opzionale)", key=f"add_gruppo_{posizione}")
            colonna_rip, colonna_rec = st.columns(2)
            with colonna_rip:
                ripetizioni = st.text_input("Ripetizioni", key=f"add_rip_{posizione}")
            with colonna_rec:
                recupero = st.text_input("Recupero", key=f"add_rec_{posizione}")
            spiegazione = st.text_area("Spiegazione", key=f"add_spieg_{posizione}")
            note = st.text_area("Note", key=f"add_note_{posizione}")
            if st.form_submit_button("Aggiungi esercizio"):
                if nome.strip():
                    _inserisci_esercizi(
                        posizione,
                        [_nuovo_esercizio(nome.strip(), spiegazione, note, ripetizioni, recupero, gruppo.strip())],
                    )
                    st.rerun()
                else:
                    st.warning("Il nome dell'esercizio e' obbligatorio.")

        st.markdown("---")
        st.caption("📦 Da scheda esistente:")
        if st.button("🎯 Inserisci un singolo esercizio da scheda", key=f"imp_singolo_{posizione}", use_container_width=True):
            percorso = _apri_file_nativo(
                [("File scheda", "*.scheda"), ("Archivio zip", "*.zip"), ("Tutti i file", "*.*")],
                "Scegli scheda da cui pescare un esercizio",
            )
            if percorso is None:
                st.error("File browser non disponibile. Avvia l'app in locale.")
            elif percorso:
                if os.path.exists(percorso):
                    try:
                        righe, _ = carica_scheda(
                            percorso, cartella_lavoro_per_bundle(percorso, base_dir=APP_BASE_DIR)
                        )
                    except (SchedaFileError, ValueError) as errore:
                        st.error(str(errore))
                    except Exception as errore:
                        st.error(f"Errore durante la lettura della scheda: {errore}")
                    else:
                        st.session_state["pending_single_import"] = {
                            "posizione": posizione,
                            "sorgente": percorso,
                            "esercizi": [_esercizio_da_riga(r) for r in righe],
                        }
                        st.rerun()
                else:
                    st.warning("Il file selezionato non esiste.")

        if st.button("📦 Importa intera scheda qui", key=f"imp_scheda_{posizione}", use_container_width=True):
            percorso = _apri_file_nativo(
                [("File scheda", "*.scheda"), ("Archivio zip", "*.zip"), ("Tutti i file", "*.*")],
                "Importa scheda",
            )
            if percorso is None:
                st.error("File browser non disponibile. Avvia l'app in locale.")
            elif percorso:
                if os.path.exists(percorso):
                    try:
                        righe, _ = carica_scheda(
                            percorso, cartella_lavoro_per_bundle(percorso, base_dir=APP_BASE_DIR)
                        )
                    except (SchedaFileError, ValueError) as errore:
                        st.error(str(errore))
                    except Exception as errore:
                        st.error(f"Errore durante la lettura della scheda: {errore}")
                    else:
                        # Mostra il selettore per scegliere quali esercizi inserire (tutti o uno)
                        st.session_state["pending_single_import"] = {
                            "posizione": posizione,
                            "sorgente": percorso,
                            "esercizi": [_esercizio_da_riga(r) for r in righe],
                        }
                        st.rerun()
                else:
                    st.warning("Il file selezionato non esiste.")

        st.markdown("---")
        if st.button("📄 Importa CSV qui", key=f"imp_csv_{posizione}", use_container_width=True):
            percorso = _apri_file_nativo([("CSV", "*.csv"), ("Tutti i file", "*.*")], "Importa CSV")
            if percorso is None:
                st.error("File browser non disponibile. Avvia l'app in locale.")
            elif percorso:
                try:
                    righe = parse_esercizi_csv(percorso)
                except ValueError as errore:
                    st.error(str(errore))
                except Exception as errore:
                    st.error(f"Errore durante la lettura del CSV: {errore}")
                else:
                    nuovi = [_esercizio_da_riga(r) for r in righe]
                    _inserisci_esercizi(posizione, nuovi)
                    st.success(f"Importati {len(nuovi)} esercizi.")
                    st.rerun()


def _campo_gruppo(esercizio, uid):
    """
    Selectbox del gruppo che suggerisce i gruppi gia' usati nella scheda, con
    opzione per inserirne uno nuovo a mano. Ritorna il gruppo scelto (str).
    """
    gruppi_esistenti = sorted(
        {
            (e.get("gruppo") or "").strip()
            for e in st.session_state["esercizi"]
            if (e.get("gruppo") or "").strip()
        }
    )
    gruppo_corrente = (esercizio.get("gruppo") or "").strip()
    senza = "(nessun gruppo)"
    nuovo = "➕ Nuovo gruppo…"
    if gruppo_corrente and gruppo_corrente not in gruppi_esistenti:
        gruppi_esistenti = sorted(set(gruppi_esistenti) | {gruppo_corrente})
    opzioni = [senza] + gruppi_esistenti + [nuovo]
    indice_default = opzioni.index(gruppo_corrente) if gruppo_corrente in opzioni else 0
    scelta = st.selectbox("Gruppo", opzioni, index=indice_default, key=f"gruppo_sel_{uid}")
    if scelta == nuovo:
        return st.text_input("Nuovo gruppo", value="", key=f"gruppo_nuovo_{uid}").strip()
    if scelta == senza:
        return ""
    return scelta


def _esercizio_pronto(esercizio):
    """True se i frame START e FINISH esistono su disco (esercizio pronto)."""
    frame_start = esercizio.get("frame_start")
    frame_finish = esercizio.get("frame_finish")
    return bool(
        frame_start and frame_finish
        and os.path.exists(frame_start) and os.path.exists(frame_finish)
    )


def _render_esercizio(i, esercizio):
    """
    Renderizza l'expander di un singolo esercizio con i due sotto-tab
    (Dettagli / Video & Frame). Ritorna una tupla (indice_da_rimuovere,
    spostamento) con l'eventuale azione richiesta dai pulsanti (o None);
    spostamento è una coppia (indici, posizione_1based) per _sposta_esercizi.
    """
    indice_da_rimuovere = None
    spostamento = None
    numero_esercizi = len(st.session_state["esercizi"])

    if "uid" not in esercizio:
        esercizio["uid"] = uuid.uuid4().hex[:8]
    uid = esercizio["uid"]

    etichetta = esercizio["nome"] or f"Esercizio {i + 1}"
    gruppo_esercizio = (esercizio.get("gruppo") or "").strip()
    prefisso_gruppo = f"[{gruppo_esercizio}] " if gruppo_esercizio else ""
    badge = "✅" if _esercizio_pronto(esercizio) else "⚠️"

    with st.expander(f"{badge} {i + 1}. {prefisso_gruppo}{etichetta}", expanded=False):
        tab_dettagli, tab_video = st.tabs(["📝 Dettagli", "🎬 Video & Frame"])

        with tab_dettagli:
            gruppo_modificato = _campo_gruppo(esercizio, uid)
            nome_modificato = st.text_input("Nome esercizio", value=esercizio["nome"], key=f"nome_{uid}")
            spiegazione_modificata = st.text_area(
                "Spiegazione", value=esercizio["spiegazione"], key=f"spiegazione_{uid}"
            )
            note_modificate = st.text_area("Note", value=esercizio["note"], key=f"note_{uid}")
            colonna_rip_edit, colonna_rec_edit = st.columns(2)
            with colonna_rip_edit:
                ripetizioni_modificate = st.text_input(
                    "Ripetizioni", value=esercizio["ripetizioni"], key=f"ripetizioni_{uid}"
                )
            with colonna_rec_edit:
                recupero_modificato = st.text_input(
                    "Recupero", value=esercizio["recupero"], key=f"recupero_{uid}"
                )

            st.session_state["esercizi"][i].update(
                {
                    "nome": nome_modificato,
                    "spiegazione": spiegazione_modificata,
                    "note": note_modificate,
                    "ripetizioni": ripetizioni_modificate,
                    "recupero": recupero_modificato,
                    "gruppo": gruppo_modificato,
                }
            )

            st.markdown("---")
            colonna_posizione, colonna_sposta, colonna_rimuovi = st.columns(
                [1, 1, 2], vertical_alignment="bottom"
            )
            with colonna_posizione:
                posizione_scelta = _numero_posizione(
                    f"pos_{uid}", i + 1, numero_esercizi, etichetta="Posizione"
                )
            with colonna_sposta:
                if st.button(
                    "↕️ Sposta",
                    key=f"sposta_{uid}",
                    use_container_width=True,
                    disabled=(numero_esercizi < 2),
                    help="Porta l'esercizio alla posizione scelta: gli altri scorrono di conseguenza",
                ):
                    spostamento = ([i], posizione_scelta)
            with colonna_rimuovi:
                if st.button("🗑️ Rimuovi esercizio", key=f"rimuovi_{uid}", use_container_width=True):
                    indice_da_rimuovere = i

        with tab_video:
            st.subheader("Ricerca video YouTube")
            if st.button("🔍 Cerca su YouTube", key=f"cerca_{uid}"):
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
                    key=f"radio_video_{uid}",
                )
                video_selezionato_url = risultati_mostrati[scelta]["webpage_url"]

            url_manuale = st.text_input(
                "Oppure incolla un URL YouTube diretto",
                value=esercizio.get("video_url") or "",
                key=f"url_manuale_{uid}",
            )

            if url_manuale.strip():
                video_url_finale = url_manuale.strip()
            elif video_selezionato_url:
                video_url_finale = video_selezionato_url
            else:
                video_url_finale = ""
            st.session_state["esercizi"][i]["video_url"] = video_url_finale

            if video_url_finale:
                st.link_button("▶️ Apri su YouTube", video_url_finale)

            st.subheader("Timestamp ed estrazione frame")
            colonna_start, colonna_finish = st.columns(2)
            with colonna_start:
                ts_start = st.number_input(
                    "Timestamp START (sec)",
                    min_value=0.0,
                    step=0.5,
                    value=float(esercizio.get("ts_start") or 0.0),
                    key=f"ts_start_{uid}",
                )
            with colonna_finish:
                ts_finish = st.number_input(
                    "Timestamp FINISH (sec)",
                    min_value=0.0,
                    step=0.5,
                    value=float(esercizio.get("ts_finish") or 1.0),
                    key=f"ts_finish_{uid}",
                )
            st.session_state["esercizi"][i]["ts_start"] = ts_start
            st.session_state["esercizi"][i]["ts_finish"] = ts_finish

            timestamp_validi = ts_finish > ts_start
            if not timestamp_validi:
                st.warning("Il timestamp FINISH deve essere maggiore del timestamp START.")

            if st.button("🎬 Estrai frame", key=f"estrai_{uid}"):
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
                                output_dir=cartella_frames(st.session_state["cartella_lavoro"]),
                            )
                        st.session_state["esercizi"][i]["frame_start"] = percorso_start
                        st.session_state["esercizi"][i]["frame_finish"] = percorso_finish
                        st.success("Frame estratti con successo.")
                    except (VideoSearchError, FrameExtractionError) as errore:
                        st.error(str(errore))
                    except Exception as errore:
                        st.error(f"Errore imprevisto durante l'estrazione dei frame: {errore}")

            st.subheader("Immagini tue al posto dei frame")
            st.caption(
                "Se il video non rende bene (o non c'è), puoi usare due immagini "
                "tue: sostituiscono i frame estratti e finiscono nella scheda e nel "
                "documento esattamente allo stesso modo."
            )
            colonna_carica_start, colonna_carica_finish = st.columns(2)
            for colonna, suffisso, etichetta in (
                (colonna_carica_start, "start", "START"),
                (colonna_carica_finish, "finish", "FINISH"),
            ):
                with colonna:
                    if st.button(
                        f"🖼️ Scegli immagine {etichetta}",
                        key=f"immagine_{suffisso}_{uid}",
                        use_container_width=True,
                    ):
                        _importa_immagine(i, suffisso)

            frame_start = st.session_state["esercizi"][i].get("frame_start")
            frame_finish = st.session_state["esercizi"][i].get("frame_finish")
            colonna_img_start, colonna_img_finish = st.columns(2)
            for colonna, percorso, suffisso, etichetta in (
                (colonna_img_start, frame_start, "start", "START"),
                (colonna_img_finish, frame_finish, "finish", "FINISH"),
            ):
                if not (percorso and os.path.exists(percorso)):
                    continue
                with colonna:
                    st.image(percorso, caption=etichetta)
                    with st.expander(f"✂️ Ritaglia {etichetta}"):
                        _ui_ritaglio_frame(percorso, uid, suffisso)

    return indice_da_rimuovere, spostamento


def _sidebar(titolo_default="SCHEDA 1: GAMBE & GLUTEI"):
    """Renderizza la barra laterale e ritorna il titolo scheda corrente."""
    titolo_da_caricare = st.session_state.pop("titolo_scheda_da_caricare", None)
    if titolo_da_caricare is not None:
        st.session_state["titolo_scheda"] = titolo_da_caricare
    with st.sidebar:
        st.title("🏋️ Workout Sheet Automator")
        titolo_scheda = st.text_input("Titolo scheda", value=titolo_default, key="titolo_scheda")

        if st.session_state.get("snapshot_salvato") == _snapshot_esercizi(st.session_state["esercizi"], titolo_scheda):
            st.caption("✅ Salvato")
        else:
            st.caption("⚠️ Modifiche non salvate")

        st.markdown("---")
        st.subheader("💾 Scheda")
        if "percorso_scheda" not in st.session_state:
            st.session_state["percorso_scheda"] = "scheda.scheda"
        percorso_scheda = st.session_state["percorso_scheda"]
        st.caption(f"File corrente: {percorso_scheda}")
        cartella_lavoro = cartella_lavoro_per_bundle(percorso_scheda, base_dir=APP_BASE_DIR)
        st.session_state["cartella_lavoro"] = cartella_lavoro

        if st.button("📂 Importa scheda", use_container_width=True):
            percorso = _apri_file_nativo(
                [("File scheda", "*.scheda"), ("Archivio zip", "*.zip"), ("Tutti i file", "*.*")],
                "Importa scheda",
            )
            if percorso is None:
                st.error("File browser non disponibile. Avvia l'app in locale.")
            elif percorso:
                if os.path.exists(percorso):
                    try:
                        lavoro_importato = cartella_lavoro_per_bundle(percorso, base_dir=APP_BASE_DIR)
                        righe, _ = carica_scheda(percorso, lavoro_importato)
                    except (SchedaFileError, ValueError) as errore:
                        st.error(str(errore))
                    except Exception as errore:
                        st.error(f"Errore durante la lettura della scheda: {errore}")
                    else:
                        st.session_state["import_pending"] = {
                            "esercizi": [_esercizio_da_riga(r) for r in righe],
                            "sorgente": percorso,
                            "tipo": "scheda",
                            "titolo": titolo_scheda_salvato(lavoro_importato),
                        }
                        st.rerun()
                else:
                    st.warning("Il file selezionato non esiste.")

        if st.button("📄 Importa CSV", use_container_width=True):
            percorso = _apri_file_nativo([("CSV", "*.csv"), ("Tutti i file", "*.*")], "Importa CSV")
            if percorso is None:
                st.error("File browser non disponibile. Avvia l'app in locale.")
            elif percorso:
                try:
                    righe = parse_esercizi_csv(percorso)
                except ValueError as errore:
                    st.error(str(errore))
                except Exception as errore:
                    st.error(f"Errore durante la lettura del CSV: {errore}")
                else:
                    st.session_state["import_pending"] = {
                        "esercizi": [_esercizio_da_riga(r) for r in righe],
                        "sorgente": percorso,
                        "tipo": "csv",
                    }
                    st.rerun()

        pendente = st.session_state.get("import_pending")
        if pendente:
            st.info(
                f"Trovati {len(pendente['esercizi'])} esercizi in "
                f"«{os.path.basename(pendente['sorgente'])}». Cosa vuoi fare?"
            )
            colonna_sost, colonna_agg, colonna_ann = st.columns(3)
            with colonna_sost:
                if st.button("Sostituisci", key="import_sostituisci"):
                    st.session_state["esercizi"] = list(pendente["esercizi"])
                    if pendente["tipo"] == "scheda":
                        st.session_state["percorso_scheda"] = pendente["sorgente"]
                        st.session_state["cartella_lavoro"] = cartella_lavoro_per_bundle(
                            pendente["sorgente"], base_dir=APP_BASE_DIR
                        )
                        if pendente.get("titolo") is not None:
                            st.session_state["titolo_scheda_da_caricare"] = pendente["titolo"]
                            st.session_state["snapshot_salvato"] = _snapshot_esercizi(
                                st.session_state["esercizi"], pendente["titolo"]
                            )
                        else:
                            # Bundle legacy senza titolo: usa il titolo corrente in sessione
                            st.session_state["snapshot_salvato"] = _snapshot_esercizi(
                                st.session_state["esercizi"], st.session_state.get("titolo_scheda", "")
                            )
                    else:
                        st.session_state["snapshot_salvato"] = _snapshot_esercizi(
                            st.session_state["esercizi"], st.session_state.get("titolo_scheda", "")
                        )
                    st.session_state["import_pending"] = None
                    st.rerun()
            with colonna_agg:
                if st.button("Aggiungi", key="import_aggiungi"):
                    st.session_state["esercizi"].extend(pendente["esercizi"])
                    st.session_state["import_pending"] = None
                    st.rerun()
            with colonna_ann:
                if st.button("Annulla", key="import_annulla"):
                    st.session_state["import_pending"] = None
                    st.rerun()

        if st.button("💾 Salva scheda", use_container_width=True):
            destinazione = _salva_file_nativo(percorso_scheda)
            if destinazione is None:
                st.error("File browser non disponibile. Avvia l'app in locale.")
            elif destinazione:
                try:
                    stato_corrente = percorso_stato(st.session_state["cartella_lavoro"])
                    salva_scheda(
                        st.session_state["esercizi"],
                        destinazione,
                        state_path=stato_corrente if os.path.exists(stato_corrente) else None,
                        titolo=titolo_scheda,
                    )
                    # Sincronizza la cache di lavoro della destinazione: il bundle è la fonte
                    # di verità ma l'UI legge subito da <destinazione>.work/state.json.
                    if os.path.exists(stato_corrente):
                        dest_lavoro = cartella_lavoro_per_bundle(destinazione, base_dir=APP_BASE_DIR)
                        try:
                            os.makedirs(dest_lavoro, exist_ok=True)
                            shutil.copy2(stato_corrente, percorso_stato(dest_lavoro))
                        except OSError:
                            pass
                except Exception as errore:
                    st.error(f"Errore durante il salvataggio della scheda: {errore}")
                else:
                    st.session_state["percorso_scheda"] = destinazione
                    st.session_state["cartella_lavoro"] = cartella_lavoro_per_bundle(
                        destinazione, base_dir=APP_BASE_DIR
                    )
                    st.session_state["snapshot_salvato"] = _snapshot_esercizi(st.session_state["esercizi"], titolo_scheda)
                    st.success(f"Scheda salvata in '{destinazione}' ({len(st.session_state['esercizi'])} esercizi).")
                    st.rerun()

        if st.button("🗑️ Svuota lista", use_container_width=True):
            st.session_state["conferma_svuota"] = True
            st.rerun()
        if st.session_state.get("conferma_svuota"):
            st.warning("Eliminare TUTTI gli esercizi dalla lista?")
            colonna_si, colonna_no = st.columns(2)
            with colonna_si:
                if st.button("✅ Sì", key="svuota_si"):
                    st.session_state["esercizi"] = []
                    st.session_state["conferma_svuota"] = False
                    st.rerun()
            with colonna_no:
                if st.button("❌ No", key="svuota_no"):
                    st.session_state["conferma_svuota"] = False
                    st.rerun()

        st.markdown("---")
        st.subheader("📤 Esporta")
        esercizi_pronti = [e for e in st.session_state["esercizi"] if _esercizio_pronto(e)]
        st.caption(f"Pronti: {len(esercizi_pronti)} / {len(st.session_state['esercizi'])}")
        if st.session_state.get("conferma_esporta"):
            st.warning(f"Generare il Google Doc con {len(esercizi_pronti)} esercizi pronti?")
            colonna_gen, colonna_ann_exp = st.columns(2)
            with colonna_gen:
                if st.button("✅ Genera", key="esporta_si"):
                    st.session_state["conferma_esporta"] = False
                    st.session_state["_esegui_esporta"] = True
                    st.rerun()
            with colonna_ann_exp:
                if st.button("❌ Annulla", key="esporta_no"):
                    st.session_state["conferma_esporta"] = False
                    st.rerun()
        else:
            if st.button(
                "📤 Esporta documento",
                use_container_width=True,
                disabled=(len(esercizi_pronti) == 0),
            ):
                st.session_state["conferma_esporta"] = True
                st.rerun()

        url_doc = _url_doc_corrente()
        if url_doc:
            st.link_button("📄 Apri Google Doc", url_doc, use_container_width=True)
        st.link_button("📁 Apri cartella Drive", URL_CARTELLA_DRIVE, use_container_width=True)

        st.markdown("---")
        st.subheader("Credenziali Google")
        credenziali_presenti = any(
            os.path.exists(percorso)
            for percorso in (
                GOOGLE_CREDENTIALS.credentials_path,
                GOOGLE_CREDENTIALS.service_account_path,
                GOOGLE_CREDENTIALS.token_path,
            )
        )
        if credenziali_presenti:
            st.success("Credenziali Google trovate.")
        else:
            st.warning(
                "Nessuna credenziale Google trovata. Per generare il documento serve "
                "'credentials.json' (OAuth) oppure 'service_account.json' nella cartella "
                "principale del progetto. Consulta il README per le istruzioni complete."
            )

    return titolo_scheda


def _esegui_esportazione(titolo_scheda):
    """Genera il Google Doc con gli esercizi pronti e risalva la scheda."""
    esercizi_pronti = [e for e in st.session_state["esercizi"] if _esercizio_pronto(e)]
    if not esercizi_pronti:
        st.error("Nessun esercizio pronto: servono i frame START e FINISH estratti.")
        return
    try:
        with st.spinner("Generazione del documento su Google Docs in corso..."):
            stato_scheda = percorso_stato(st.session_state["cartella_lavoro"])
            risultato = create_workout_document(
                esercizi_pronti,
                titolo_scheda,
                state_path=stato_scheda,
                credential_provider=GOOGLE_CREDENTIALS,
            )
        if risultato.get("documento_rigenerato"):
            st.info(
                "Il documento generato in precedenza non esiste più su Drive: "
                "ne è stato creato uno nuovo con tutti gli esercizi."
            )
        st.success(f"Documento generato con successo! [Apri il documento]({risultato['url']})")
    except GoogleAuthError as errore:
        st.error(str(errore))
    except GoogleDocsError as errore:
        st.error(str(errore))
    except Exception as errore:
        st.error(f"Errore imprevisto durante la generazione del documento: {errore}")
    else:
        try:
            salva_scheda(
                st.session_state["esercizi"],
                st.session_state["percorso_scheda"],
                state_path=stato_scheda,
                titolo=titolo_scheda,
            )
            st.session_state["snapshot_salvato"] = _snapshot_esercizi(st.session_state["esercizi"], titolo_scheda)
        except Exception as errore:
            st.warning(f"Documento creato, ma salvataggio della scheda fallito: {errore}")


def main():
    st.set_page_config(page_title="Workout Sheet Automator", layout="wide", page_icon="🏋️")

    if "esercizi" not in st.session_state:
        st.session_state["esercizi"] = []

    titolo_scheda = _sidebar()

    if shutil.which("ffmpeg") is None:
        st.warning(
            "⚠️ ffmpeg non risulta installato o non è nel PATH. L'estrazione dei frame "
            "START/FINISH non funzionerà finché non lo installi (vedi README)."
        )

    if st.session_state.pop("_esegui_esporta", False):
        _esegui_esportazione(titolo_scheda)

    st.header("Anteprima e modifica scheda")

    # Banner globale per import singolo in sospeso: assicura visibilità anche se il '+' è fuori viewport
    pending_glob = st.session_state.get("pending_single_import")
    if pending_glob:
        pos = pending_glob.get("posizione", 0)
        sorg = os.path.basename(pending_glob.get("sorgente") or "")
        tot = len(pending_glob.get("esercizi") or [])
        with st.container(border=True):
            st.info(f"📦 Import in sospeso: «{sorg}» ({tot} esercizi) → posizione {pos + 1}. Scorri fino al ➕ in quella posizione per scegliere, o annulla qui.")
            if st.button("❌ Annulla import in sospeso", key="global_ann_single"):
                st.session_state["pending_single_import"] = None
                st.rerun()

    _assicura_uid()
    duplicati = trova_duplicati_slug(st.session_state["esercizi"])
    if duplicati:
        dettagli = ", ".join(
            f"'{slug}' alle posizioni {', '.join(str(i+1) for i in idx)}"
            for slug, idx in duplicati.items()
        )
        st.warning(
            f"Nomi duplicati rilevati (stesso slug): {dettagli}. "
            "I frame verranno salvati con suffisso _2, _3 per evitare sovrascritture, "
            "ma rinominare gli esercizi è consigliato."
        )
    indice_da_rimuovere = None
    spostamento = None
    numero_esercizi = len(st.session_state["esercizi"])

    if numero_esercizi == 0:
        st.info(
            "Nessun esercizio in lista. Importa una scheda o un CSV dalla barra a "
            "sinistra, oppure aggiungi un esercizio con il pulsante qui sotto."
        )
        colonna_sx, colonna_centro, colonna_dx = st.columns([2, 1, 2])
        with colonna_centro:
            _blocco_inserimento(0, etichetta="➕ Aggiungi esercizio", aiuto="Aggiungi il primo esercizio")
    else:
        _barra_azioni_multiple()
        for i, esercizio in enumerate(st.session_state["esercizi"]):
            _blocco_inserimento(i, etichetta="➕", aiuto="Inserisci un esercizio qui")
            colonna_selezione, colonna_esercizio = st.columns([1, 24], vertical_alignment="center")
            with colonna_selezione:
                st.checkbox(
                    f"Seleziona esercizio {i + 1}",
                    key=_chiave_selezione(esercizio),
                    label_visibility="collapsed",
                    help="Seleziona per spostare o eliminare più esercizi insieme",
                )
            with colonna_esercizio:
                rimuovi, sposta = _render_esercizio(i, esercizio)
            if rimuovi is not None:
                indice_da_rimuovere = rimuovi
            if sposta is not None:
                spostamento = sposta
        _blocco_inserimento(numero_esercizi, etichetta="➕ Aggiungi in fondo", aiuto="Aggiungi un esercizio in fondo")

    if indice_da_rimuovere is not None:
        _elimina_esercizi([indice_da_rimuovere])
        st.rerun()

    if spostamento is not None:
        indici, posizione = spostamento
        _sposta_esercizi(indici, posizione)
        st.rerun()


if __name__ == "__main__":
    main()
