"""
Modulo di supporto per la generazione della scheda di allenamento come
Google Doc formato A4, con layout a moduli (tabella 1x2 per esercizio:
immagini a sinistra, testo a destra), raggruppati in sezioni e con uno stato
persistente per documento che rende la generazione resumibile e permette la
sostituzione mirata dei frame di un singolo esercizio.
"""

from __future__ import annotations

import json
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import video_helper
from .csv_utils import slugify, slugs_unici
from .platform import CredentialProviderError, LocalCredentialsProvider

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

# Colore teal usato per i valori di ripetizioni/recupero.
COLORE_TEAL = {"red": 0.23, "green": 0.75, "blue": 0.70}

class GoogleAuthError(Exception):
    """Sollevata quando l'autenticazione con le API Google non è configurata o fallisce."""


class GoogleDocsError(Exception):
    """Sollevata quando una chiamata alle API Google Docs/Drive fallisce."""


def _credential_provider(credential_provider=None, base_dir: str | os.PathLike | None = None):
    return credential_provider or LocalCredentialsProvider(base_dir)


def get_credentials(*, credential_provider=None, base_dir: str | os.PathLike | None = None):
    """
    Restituisce le credenziali Google da usare per Docs/Drive.

    Modalità supportate:
      1. Service Account: se esiste 'service_account.json' viene usato direttamente
         (nessuna interazione utente necessaria, ma il documento apparterrà al SA).
      2. OAuth utente: usa/crea 'token.json' a partire da 'credentials.json',
         aprendo un flusso di autorizzazione nel browser se necessario.
    """
    try:
        return _credential_provider(credential_provider, base_dir).get_credentials(SCOPES)
    except CredentialProviderError as exc:
        raise GoogleAuthError(str(exc)) from exc


def get_credentials_manual_flow(
    auth_code: str | None = None, *, credential_provider=None, base_dir: str | os.PathLike | None = None
):
    """
    Variante di get_credentials() per ambienti headless/remoti dove non è
    disponibile un browser locale (agente, CI, sandbox): al posto di
    flow.run_local_server() separa il flusso in due chiamate esplicite.

    - Prima chiamata (auth_code=None): costruisce l'URL di autorizzazione e
      solleva GoogleAuthError con l'URL e le istruzioni per l'utente (aprire
      l'URL, autorizzare, copiare il parametro 'code' dall'URL di redirect
      anche se la pagina non si carica).
    - Seconda chiamata (auth_code=<code o URL di redirect>): completa lo
      scambio del code, salva 'token.json' come get_credentials() e
      restituisce le credenziali.

    Non usa mai service_account.json (quel path resta gestito da
    get_credentials()): questa funzione è dedicata al login OAuth utente.
    """
    try:
        return _credential_provider(credential_provider, base_dir).get_credentials_manual_flow(
            SCOPES, auth_code
        )
    except CredentialProviderError as exc:
        raise GoogleAuthError(str(exc)) from exc


def upload_image_to_drive(drive_service, image_path: str) -> tuple[str, str]:
    """
    Carica un'immagine su Google Drive e la rende accessibile pubblicamente
    in lettura (necessario perché Google Docs possa incorporarla via URI).
    Restituisce (file_id, uri_pubblico).
    """
    try:
        metadata = {"name": os.path.basename(image_path)}
        media = MediaFileUpload(image_path, mimetype="image/jpeg")
        file = drive_service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute()
        file_id = file["id"]
        drive_service.permissions().create(
            fileId=file_id, body={"role": "reader", "type": "anyone"}
        ).execute()
        return file_id, f"https://drive.google.com/uc?id={file_id}"
    except HttpError as exc:
        raise GoogleDocsError(
            f"Errore durante il caricamento dell'immagine '{image_path}' su Google Drive: {exc}"
        ) from exc


def delete_drive_file(drive_service, file_id: str) -> None:
    """Elimina un file da Drive in modo best-effort (nessun errore bloccante)."""
    try:
        drive_service.files().delete(fileId=file_id).execute()
    except Exception:
        pass


def carica_stato(percorso: str) -> dict | None:
    """Carica lo stato (JSON, UTF-8) di una scheda da file, o None se il file non esiste."""
    if not os.path.exists(percorso):
        return None
    with open(percorso, "r", encoding="utf-8") as file_stato:
        return json.load(file_stato)


def salva_stato(percorso: str, stato: dict) -> None:
    """Salva su file (JSON, UTF-8) lo stato di una scheda: doc_id, titolo ed esercizi inseriti."""
    with open(percorso, "w", encoding="utf-8") as file_stato:
        json.dump(stato, file_stato, ensure_ascii=False, indent=2)


def percorso_stato_per_titolo(doc_title: str) -> str:
    """Restituisce il percorso convenzionale del file di stato per una scheda, dedotto dal titolo."""
    return f"{slugify(doc_title)}.state.json"


def _dimensione_pt(magnitude: float) -> dict:
    return {"magnitude": magnitude, "unit": "PT"}


def _richiesta_stile_testo(start: int, end: int, stile: dict) -> dict:
    """Costruisce una richiesta updateTextStyle a partire da un dizionario semplificato."""
    text_style = {}
    campi = []
    if stile.get("bold"):
        text_style["bold"] = True
        campi.append("bold")
    if stile.get("size"):
        text_style["fontSize"] = _dimensione_pt(stile["size"])
        campi.append("fontSize")
    if stile.get("color"):
        text_style["foregroundColor"] = {"color": {"rgbColor": stile["color"]}}
        campi.append("foregroundColor")
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": text_style,
            "fields": ",".join(campi),
        }
    }


def _segmenti_cella_destra(esercizio: dict) -> list[tuple[str, dict]]:
    """
    Costruisce la lista di segmenti (testo, stile) che compongono il contenuto
    testuale della cella destra del modulo esercizio.
    """
    nome = str(esercizio.get("nome", "")).upper()
    spiegazione = str(esercizio.get("spiegazione", ""))
    note = str(esercizio.get("note", ""))
    ripetizioni = str(esercizio.get("ripetizioni", ""))
    recupero = str(esercizio.get("recupero", ""))

    return [
        (nome, {"bold": True, "size": 16}),
        ("\n\n", {}),
        ("SPIEGAZIONE & NOTE", {"bold": True, "size": 9}),
        ("\n", {}),
        (spiegazione, {"size": 9}),
        ("\n", {}),
        ("NOTE: ", {"bold": True, "size": 9}),
        (note, {"size": 9}),
        ("\n\n", {}),
        ("RIPETIZIONI", {"bold": True, "size": 9}),
        ("\n", {}),
        (ripetizioni, {"bold": True, "size": 14, "color": COLORE_TEAL}),
        ("\n", {}),
        ("RECUPERO", {"bold": True, "size": 9}),
        ("\n", {}),
        (recupero, {"bold": True, "size": 14, "color": COLORE_TEAL}),
    ]


def _richieste_cella_destra(right_start: int, esercizio: dict) -> list[dict]:
    """
    Costruisce le richieste per popolare la cella destra: un unico insertText
    con tutto il testo, seguito dagli updateTextStyle sui range calcolati in
    base alle lunghezze note di ciascun segmento.
    """
    segmenti = _segmenti_cella_destra(esercizio)
    testo_completo = "".join(testo for testo, _ in segmenti)

    richieste = [
        {"insertText": {"location": {"index": right_start}, "text": testo_completo}}
    ]

    offset = 0
    for testo, stile in segmenti:
        lunghezza = len(testo)
        # I segmenti vuoti (campo dell'esercizio non compilato: note,
        # spiegazione, ripetizioni o recupero) non vanno stilizzati: un
        # updateTextStyle con startIndex == endIndex fa fallire l'intero
        # batchUpdate con "The range should not be empty".
        if stile and lunghezza:
            inizio = right_start + offset
            fine = inizio + lunghezza
            richieste.append(_richiesta_stile_testo(inizio, fine, stile))
        offset += lunghezza

    return richieste


def _richieste_cella_sinistra(left_start: int, uri_start: str, uri_finish: str) -> list[dict]:
    """
    Costruisce le richieste per popolare la cella sinistra: etichette testuali
    e immagini inline, inserite in sequenza tenendo traccia manualmente della
    posizione corrente (ogni insertText sposta gli indici di N caratteri,
    ogni insertInlineImage occupa esattamente 1 indice).
    """
    richieste = []
    pos = left_start
    larghezza_immagine = {"magnitude": 200, "unit": "PT"}

    # Etichetta "START"
    etichetta_start = "START\n"
    richieste.append({"insertText": {"location": {"index": pos}, "text": etichetta_start}})
    richieste.append(_richiesta_stile_testo(pos, pos + len(etichetta_start), {"bold": True, "size": 9}))
    pos += len(etichetta_start)

    # Immagine frame di partenza
    richieste.append(
        {
            "insertInlineImage": {
                "location": {"index": pos},
                "uri": uri_start,
                "objectSize": {"width": larghezza_immagine},
            }
        }
    )
    pos += 1  # un'immagine inline occupa un solo indice nel documento

    # Etichetta "FINISH" preceduta da una nuova riga
    blocco_finish = "\nFINISH\n"
    richieste.append({"insertText": {"location": {"index": pos}, "text": blocco_finish}})
    # Applichiamo lo stile solo alla parte "FINISH\n", saltando l'a-capo iniziale.
    richieste.append(
        _richiesta_stile_testo(pos + 1, pos + len(blocco_finish), {"bold": True, "size": 9})
    )
    pos += len(blocco_finish)

    # Immagine frame finale
    richieste.append(
        {
            "insertInlineImage": {
                "location": {"index": pos},
                "uri": uri_finish,
                "objectSize": {"width": larghezza_immagine},
            }
        }
    )
    pos += 1

    return richieste


def _trova_ultima_tabella(documento: dict) -> dict:
    """Restituisce l'ultimo elemento 'table' presente nel corpo del documento."""
    contenuto = documento["body"]["content"]
    for elemento in reversed(contenuto):
        if "table" in elemento:
            return elemento
    raise GoogleDocsError("Nessuna tabella trovata nel documento dopo l'inserimento.")


def _indice_fine_documento(documento: dict) -> int:
    """Restituisce l'indice utilizzabile per appendere contenuto in fondo al documento."""
    return documento["body"]["content"][-1]["endIndex"] - 1


def _inserisci_page_break(docs_service, doc_id: str) -> None:
    """Inserisce un'interruzione di pagina in fondo al documento."""
    documento = docs_service.documents().get(documentId=doc_id).execute()
    indice_break = _indice_fine_documento(documento)
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertPageBreak": {"location": {"index": indice_break}}}]},
    ).execute()


def _inserisci_header_gruppo(docs_service, doc_id: str, nome_gruppo: str) -> None:
    """Inserisce, in fondo al documento, il paragrafo di intestazione di un gruppo/sezione."""
    documento = docs_service.documents().get(documentId=doc_id).execute()
    indice_inserimento = _indice_fine_documento(documento)
    testo_header = nome_gruppo.upper() + "\n"
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {"insertText": {"location": {"index": indice_inserimento}, "text": testo_header}},
                _richiesta_stile_testo(
                    indice_inserimento,
                    indice_inserimento + len(testo_header),
                    {"bold": True, "size": 13, "color": COLORE_TEAL},
                ),
            ]
        },
    ).execute()


def _trova_tabella_esercizio(documento: dict, slug: str, indice_esercizio: int) -> dict:
    """
    Individua l'elemento tabella di un esercizio nel documento: prima tenta
    con il named range 'esercizio_{slug}' (dict name -> namedRanges, ogni
    entry ha 'ranges'), poi in fallback usa la N-esima tabella del corpo del
    documento (N = posizione dell'esercizio nella lista dello stato),
    utile se il named range non è (più) presente.
    """
    named_ranges = documento.get("namedRanges") or {}
    voci = named_ranges.get(f"esercizio_{slug}")
    if voci and voci.get("namedRanges"):
        range_tabella = voci["namedRanges"][0]["ranges"][0]
        start_index = range_tabella["startIndex"]
        for elemento in documento["body"]["content"]:
            if "table" in elemento and elemento["startIndex"] == start_index:
                return elemento
        raise GoogleDocsError(
            f"Named range 'esercizio_{slug}' trovato ma nessuna tabella corrispondente nel documento."
        )

    # Fallback: N-esima tabella del corpo, nell'ordine di apparizione.
    tabelle = [elemento for elemento in documento["body"]["content"] if "table" in elemento]
    if indice_esercizio >= len(tabelle):
        raise GoogleDocsError(
            f"Impossibile individuare la tabella dell'esercizio (indice {indice_esercizio}, "
            f"{len(tabelle)} tabelle presenti nel documento)."
        )
    return tabelle[indice_esercizio]


def _stato_http(exc: HttpError) -> int | None:
    """Codice HTTP di un HttpError, robusto alle varianti di googleapiclient."""
    risposta = getattr(exc, "resp", None)
    stato = getattr(risposta, "status", None)
    if stato is None:
        stato = getattr(exc, "status_code", None)
    try:
        return int(stato) if stato is not None else None
    except (TypeError, ValueError):
        return None


def _documento_raggiungibile(docs_service, doc_id: str) -> bool:
    """
    True se il documento esiste ancora, False se Google risponde 404 (documento
    eliminato definitivamente da Drive). Ogni altro errore HTTP viene
    propagato come GoogleDocsError: un problema di permessi o di rete non deve
    far creare un doppione del documento.
    """
    try:
        docs_service.documents().get(documentId=doc_id).execute()
    except HttpError as exc:
        if _stato_http(exc) == 404:
            return False
        raise GoogleDocsError(
            f"Il documento '{doc_id}' non è accessibile: {exc}"
        ) from exc
    return True


def _crea_documento_scheda(docs_service, doc_title: str, state_path: str | None) -> tuple[str, dict]:
    """
    Crea un nuovo Google Doc per la scheda: formato A4 verticale con margini
    di 36pt e titolo centrato in grassetto. Ritorna (doc_id, stato) con lo
    stato iniziale già salvato su state_path se indicato.
    """
    documento = docs_service.documents().create(body={"title": doc_title}).execute()
    doc_id = documento["documentId"]

    # Impostiamo il formato pagina A4 verticale (in punti) e margini di 36pt.
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "updateDocumentStyle": {
                        "documentStyle": {
                            "pageSize": {
                                "width": _dimensione_pt(595.28),
                                "height": _dimensione_pt(841.89),
                            },
                            "marginTop": _dimensione_pt(36),
                            "marginBottom": _dimensione_pt(36),
                            "marginLeft": _dimensione_pt(36),
                            "marginRight": _dimensione_pt(36),
                        },
                        "fields": "pageSize,marginTop,marginBottom,marginLeft,marginRight",
                    }
                }
            ]
        },
    ).execute()

    # Titolo della scheda, centrato e in grassetto.
    titolo_testo = doc_title.upper() + "\n"
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {"insertText": {"location": {"index": 1}, "text": titolo_testo}},
                _richiesta_stile_testo(1, 1 + len(titolo_testo), {"bold": True, "size": 18}),
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": 1, "endIndex": 1 + len(titolo_testo)},
                        "paragraphStyle": {"alignment": "CENTER"},
                        "fields": "alignment",
                    }
                },
            ]
        },
    ).execute()

    stato = {
        "doc_id": doc_id,
        "titolo": doc_title,
        "url": f"https://docs.google.com/document/d/{doc_id}/edit",
        "esercizi": [],
    }
    if state_path:
        salva_stato(state_path, stato)
    return doc_id, stato


def create_workout_document(
    exercises: list[dict],
    doc_title: str,
    docs_service=None,
    drive_service=None,
    state_path: str | None = None,
    page_break_per_gruppo: bool = True,
    *,
    credential_provider=None,
    base_dir: str | os.PathLike | None = None,
) -> dict:
    """
    Crea (o riprende) un Google Doc A4 verticale con un modulo per ogni
    esercizio (tabella 1x2: immagini a sinistra, dettagli testuali a
    destra), raggruppati per la chiave 'gruppo' di ciascun esercizio
    (stringa vuota = gruppo implicito, nessuna intestazione, mantenendo
    l'ordine di prima apparizione dei gruppi).

    Se state_path è valorizzato, lo stato della scheda (doc_id + esercizi già
    inseriti) viene salvato su disco dopo OGNI esercizio completato: una
    successiva chiamata con lo stesso state_path riusa il documento esistente
    e salta gli esercizi il cui slug è già presente nello stato, rendendo la
    generazione resumibile dopo un'interruzione. Con state_path=None il
    comportamento è quello "in un colpo solo" di sempre (nessun file
    scritto), ma la logica di raggruppamento si applica comunque.

    Se il documento indicato dallo stato non esiste più (404: cancellato da
    Drive), lo stato viene considerato orfano e la scheda viene rigenerata da
    zero in un documento nuovo con tutti gli esercizi — non è un errore. Ogni
    altro errore di accesso al documento (permessi, rete) resta un
    GoogleDocsError, per non creare doppioni.

    Restituisce {"document_id", "url", "esercizi_inseriti": [nomi inseriti
    in QUESTA esecuzione], "documento_rigenerato": bool}.

    docs_service e drive_service possono essere passati esplicitamente (utile
    per i test con mock); se omessi vengono costruiti a partire dalle
    credenziali restituite da get_credentials().
    """
    if docs_service is None or drive_service is None:
        creds = get_credentials(credential_provider=credential_provider, base_dir=base_dir)
        if docs_service is None:
            docs_service = build("docs", "v1", credentials=creds)
        if drive_service is None:
            drive_service = build("drive", "v3", credentials=creds)

    file_id_caricati: list[str] = []
    esercizi_inseriti: list[str] = []

    try:
        stato = carica_stato(state_path) if state_path else None
        doc_id = stato.get("doc_id") if stato else None
        documento_rigenerato = False

        if doc_id and not _documento_raggiungibile(docs_service, doc_id):
            # Il documento a cui punta lo stato non esiste più (eliminato
            # definitivamente da Drive): lo stato è orfano, quindi lo si
            # scarta e si riparte da un documento nuovo con TUTTI gli
            # esercizi, invece di fallire lasciando la scheda inesportabile.
            doc_id = None
            stato = None
            documento_rigenerato = True

        if doc_id is None:
            # Ripresa di una scheda già iniziata: riusiamo il documento
            # esistente; altrimenti (o se è appena sparito) ne creiamo uno.
            doc_id, stato = _crea_documento_scheda(docs_service, doc_title, state_path)

        slug_già_inseriti = {voce["slug"] for voce in stato["esercizi"]}
        # Mappa esercizio id -> slug unico per gestire omonimi (squat, squat_2)
        # L'ordine è quello di 'exercises' così la ripresa è deterministica.
        slugs_unici_lista = slugs_unici(exercises)
        slug_per_id = {id(ex): slug for ex, slug in zip(exercises, slugs_unici_lista)}

        # Raggruppiamo gli esercizi per 'gruppo' mantenendo l'ordine di prima apparizione.
        gruppi: dict[str, list[dict]] = {}
        for esercizio in exercises:
            chiave_gruppo = str(esercizio.get("gruppo") or "")
            gruppi.setdefault(chiave_gruppo, []).append(esercizio)

        # True se il documento ha già del contenuto (esercizi) prima di questa
        # esecuzione o dei gruppi già processati in questa stessa esecuzione:
        # serve per decidere se inserire un page break al cambio di gruppo
        # (mai prima del primissimo contenuto del documento).
        contenuto_già_presente = bool(stato["esercizi"])

        for nome_gruppo, esercizi_gruppo in gruppi.items():
            gruppo_già_iniziato = any(voce["gruppo"] == nome_gruppo for voce in stato["esercizi"])

            if not gruppo_già_iniziato:
                if contenuto_già_presente and page_break_per_gruppo:
                    _inserisci_page_break(docs_service, doc_id)
                if nome_gruppo:
                    _inserisci_header_gruppo(docs_service, doc_id, nome_gruppo)
                contenuto_già_presente = True

            numero_esercizi_gruppo = len(esercizi_gruppo)
            for posizione, esercizio in enumerate(esercizi_gruppo):
                slug = slug_per_id[id(esercizio)]
                if slug in slug_già_inseriti:
                    # Già presente nello stato (esecuzione precedente interrotta): saltiamo.
                    continue

                # Carichiamo prima le immagini su Drive: ci servono gli URI pubblici
                # per poterle referenziare nell'insertInlineImage.
                start_id, uri_start = upload_image_to_drive(drive_service, esercizio["frame_start"])
                file_id_caricati.append(start_id)
                finish_id, uri_finish = upload_image_to_drive(drive_service, esercizio["frame_finish"])
                file_id_caricati.append(finish_id)

                # 1. Rileggiamo il documento per trovare l'indice di fine e inseriamo la tabella.
                documento = docs_service.documents().get(documentId=doc_id).execute()
                indice_inserimento = _indice_fine_documento(documento)
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "insertTable": {
                                    "rows": 1,
                                    "columns": 2,
                                    "location": {"index": indice_inserimento},
                                }
                            }
                        ]
                    },
                ).execute()

                # 2. Rileggiamo il documento per individuare la tabella appena creata
                # e gli indici di partenza dei paragrafi vuoti nelle due celle.
                documento = docs_service.documents().get(documentId=doc_id).execute()
                elemento_tabella = _trova_ultima_tabella(documento)
                celle = elemento_tabella["table"]["tableRows"][0]["tableCells"]
                left_start = celle[0]["content"][0]["startIndex"]
                right_start = celle[1]["content"][0]["startIndex"]

                # 3. Popoliamo le celle in un unico batchUpdate: prima la cella destra
                # (indice maggiore), poi la sinistra, così gli inserimenti a sinistra
                # non invalidano gli offset già usati per la cella destra.
                richieste_popolamento = _richieste_cella_destra(right_start, esercizio)
                richieste_popolamento += _richieste_cella_sinistra(left_start, uri_start, uri_finish)
                docs_service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": richieste_popolamento}
                ).execute()

                # 4. Stile della tabella: bordi grigio chiarissimo, padding contenuto,
                # e larghezze di colonna fisse (sinistra per le immagini, destra per il testo).
                table_start = elemento_tabella["startIndex"]
                bordo = {
                    "color": {"color": {"rgbColor": {"red": 0.92, "green": 0.92, "blue": 0.92}}},
                    "width": _dimensione_pt(0.5),
                    "dashStyle": "SOLID",
                }
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "updateTableCellStyle": {
                                    "tableStartLocation": {"index": table_start},
                                    "tableCellStyle": {
                                        "borderLeft": bordo,
                                        "borderRight": bordo,
                                        "borderTop": bordo,
                                        "borderBottom": bordo,
                                        "paddingLeft": _dimensione_pt(4),
                                        "paddingRight": _dimensione_pt(4),
                                        "paddingTop": _dimensione_pt(4),
                                        "paddingBottom": _dimensione_pt(4),
                                    },
                                    "fields": (
                                        "borderLeft,borderRight,borderTop,borderBottom,"
                                        "paddingLeft,paddingRight,paddingTop,paddingBottom"
                                    ),
                                }
                            },
                            {
                                "updateTableColumnProperties": {
                                    "tableStartLocation": {"index": table_start},
                                    "columnIndices": [0],
                                    "tableColumnProperties": {
                                        "width": _dimensione_pt(220),
                                        "widthType": "FIXED_WIDTH",
                                    },
                                    "fields": "width,widthType",
                                }
                            },
                            {
                                "updateTableColumnProperties": {
                                    "tableStartLocation": {"index": table_start},
                                    "columnIndices": [1],
                                    "tableColumnProperties": {
                                        "width": _dimensione_pt(300),
                                        "widthType": "FIXED_WIDTH",
                                    },
                                    "fields": "width,widthType",
                                }
                            },
                        ]
                    },
                ).execute()

                # 5. Ancoriamo la tabella con un named range 'esercizio_{slug}', rileggendo
                # il documento per avere gli indici correnti (il popolamento ha spostato
                # l'endIndex della tabella rispetto a quando era ancora vuota).
                documento = docs_service.documents().get(documentId=doc_id).execute()
                elemento_tabella_aggiornato = _trova_ultima_tabella(documento)
                risposta_named_range = docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "createNamedRange": {
                                    "name": f"esercizio_{slug}",
                                    "range": {
                                        "startIndex": elemento_tabella_aggiornato["startIndex"],
                                        "endIndex": elemento_tabella_aggiornato["endIndex"],
                                    },
                                }
                            }
                        ]
                    },
                ).execute()
                named_range_id = risposta_named_range["replies"][0]["createNamedRange"]["namedRangeId"]

                # 6. Interruzione di pagina dopo ogni 3° esercizio del gruppo (non dopo
                # l'ultimo esercizio del gruppo).
                e_multiplo_di_tre = (posizione + 1) % 3 == 0
                e_ultimo_del_gruppo = (posizione + 1) == numero_esercizi_gruppo
                if e_multiplo_di_tre and not e_ultimo_del_gruppo and page_break_per_gruppo:
                    _inserisci_page_break(docs_service, doc_id)

                # 7. Checkpoint: registriamo subito l'esercizio nello stato e lo salviamo,
                # così un'interruzione successiva non fa perdere il lavoro già fatto.
                stato["esercizi"].append(
                    {
                        "nome": esercizio["nome"],
                        "slug": slug,
                        "named_range_id": named_range_id,
                        "gruppo": nome_gruppo,
                    }
                )
                slug_già_inseriti.add(slug)
                if state_path:
                    salva_stato(state_path, stato)
                esercizi_inseriti.append(esercizio["nome"])

        return {
            "document_id": doc_id,
            "url": f"https://docs.google.com/document/d/{doc_id}/edit",
            "esercizi_inseriti": esercizi_inseriti,
            "documento_rigenerato": documento_rigenerato,
        }
    except HttpError as exc:
        raise GoogleDocsError(
            f"Errore durante la comunicazione con le API di Google Docs/Drive: {exc}"
        ) from exc
    finally:
        # Le immagini caricate su Drive servono solo come sorgente per l'inserimento
        # nel documento: una volta incorporate possiamo eliminarle da Drive.
        for file_id in file_id_caricati:
            delete_drive_file(drive_service, file_id)


def update_exercise_media(
    doc_id: str,
    exercise_name: str,
    video_url: str | None = None,
    ts_start: float | None = None,
    ts_finish: float | None = None,
    state_path: str | None = None,
    docs_service=None,
    drive_service=None,
    output_dir: str = "frames",
    *,
    credential_provider=None,
    base_dir: str | os.PathLike | None = None,
    ffmpeg_backend=None,
) -> dict:
    """
    Sostituisce mirata mente i due frame (START/FINISH) di un esercizio già
    presente in un documento generato da create_workout_document(), senza
    rigenerare l'intero documento: ri-estrae i frame dal video indicato e
    sostituisce solo le due immagini inline nella tabella dell'esercizio
    (individuata tramite il named range 'esercizio_{slug}' salvato nello
    stato, con fallback sulla N-esima tabella del corpo del documento).

    Richiede uno state_path valido (lo stato generato da
    create_workout_document con lo stesso doc_id) per individuare
    l'esercizio: lo stato non conserva il video precedentemente usato (solo
    l'ancoraggio nel documento), quindi video_url va sempre indicato
    esplicitamente qui; se ts_start/ts_finish non sono indicati si applica
    l'euristica 10%/50% sulla durata ottenuta con get_video_info(). I nuovi
    frame vengono scritti in output_dir (per una scheda a bundle passare
    scheda_file.cartella_frames(cartella_lavoro)).

    Restituisce {"document_id", "esercizio", "frame_start", "frame_finish"}.
    """
    if not state_path:
        raise GoogleDocsError(
            "update_exercise_media richiede uno state_path valido (il file di stato generato "
            "da create_workout_document) per individuare l'esercizio nel documento."
        )
    stato = carica_stato(state_path)
    if not stato:
        raise GoogleDocsError(
            f"Nessuno stato trovato in '{state_path}'. update_exercise_media può operare solo "
            "su documenti generati con state_path (vedi create_workout_document)."
        )

    slug = slugify(exercise_name)
    lista_esercizi_stato = stato.get("esercizi", [])
    indice_esercizio = next(
        (i for i, voce in enumerate(lista_esercizi_stato) if voce["slug"] == slug), None
    )
    if indice_esercizio is None:
        raise GoogleDocsError(f"Esercizio '{exercise_name}' non trovato nello stato '{state_path}'.")

    if not video_url:
        raise GoogleDocsError(
            "update_exercise_media richiede un nuovo 'video_url' esplicito: lo stato non "
            "conserva il video precedentemente usato, solo l'ancoraggio nel documento."
        )

    if docs_service is None or drive_service is None:
        creds = get_credentials(credential_provider=credential_provider, base_dir=base_dir)
        if docs_service is None:
            docs_service = build("docs", "v1", credentials=creds)
        if drive_service is None:
            drive_service = build("drive", "v3", credentials=creds)

    if ts_start is None or ts_finish is None:
        info = video_helper.get_video_info(video_url)
        durata = info.get("duration") or 60
        if ts_start is None:
            ts_start = durata * 0.10
        if ts_finish is None:
            ts_finish = durata * 0.50

    if ffmpeg_backend is None:
        percorso_start, percorso_finish = video_helper.extract_start_finish_frames(
            video_url, ts_start, ts_finish, exercise_name, output_dir
        )
    else:
        percorso_start, percorso_finish = video_helper.extract_start_finish_frames(
            video_url, ts_start, ts_finish, exercise_name, output_dir, ffmpeg_backend=ffmpeg_backend
        )

    file_id_caricati: list[str] = []
    try:
        try:
            documento = docs_service.documents().get(documentId=doc_id).execute()
        except HttpError as exc:
            raise GoogleDocsError(f"Impossibile leggere il documento '{doc_id}': {exc}") from exc

        elemento_tabella = _trova_tabella_esercizio(documento, slug, indice_esercizio)
        celle = elemento_tabella["table"]["tableRows"][0]["tableCells"]
        prima_cella = celle[0]

        elementi_immagine = []
        for blocco in prima_cella["content"]:
            paragrafo = blocco.get("paragraph")
            if not paragrafo:
                continue
            for elemento in paragrafo.get("elements", []):
                if "inlineObjectElement" in elemento:
                    elementi_immagine.append((elemento["startIndex"], elemento["endIndex"]))
        elementi_immagine.sort(key=lambda coppia: coppia[0])

        if len(elementi_immagine) < 2:
            raise GoogleDocsError(
                f"Impossibile individuare le due immagini START/FINISH dell'esercizio "
                f"'{exercise_name}' nel documento (trovate {len(elementi_immagine)})."
            )

        start_id, uri_start = upload_image_to_drive(drive_service, percorso_start)
        file_id_caricati.append(start_id)
        finish_id, uri_finish = upload_image_to_drive(drive_service, percorso_finish)
        file_id_caricati.append(finish_id)

        # Prima immagine della cella (indice più basso) = START, seconda = FINISH.
        nuovi_uri = [uri_start, uri_finish]
        larghezza_immagine = {"magnitude": 200, "unit": "PT"}

        richieste = []
        for (start_idx, end_idx), uri in sorted(
            zip(elementi_immagine, nuovi_uri), key=lambda coppia: coppia[0][0], reverse=True
        ):
            # Ordine decrescente di indice: cancelliamo/inseriamo prima l'immagine con indice
            # più alto, così l'operazione sull'altra immagine non viene invalidata dagli offset.
            richieste.append(
                {"deleteContentRange": {"range": {"startIndex": start_idx, "endIndex": end_idx}}}
            )
            richieste.append(
                {
                    "insertInlineImage": {
                        "location": {"index": start_idx},
                        "uri": uri,
                        "objectSize": {"width": larghezza_immagine},
                    }
                }
            )

        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": richieste}).execute()

        return {
            "document_id": doc_id,
            "esercizio": exercise_name,
            "frame_start": percorso_start,
            "frame_finish": percorso_finish,
        }
    except HttpError as exc:
        raise GoogleDocsError(
            f"Errore durante la comunicazione con le API di Google Docs/Drive: {exc}"
        ) from exc
    finally:
        # Solo i nuovi file caricati per questo aggiornamento vengono ripuliti da Drive.
        for file_id in file_id_caricati:
            delete_drive_file(drive_service, file_id)
