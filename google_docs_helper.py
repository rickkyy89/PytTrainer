"""
Modulo di supporto per la generazione della scheda di allenamento come
Google Doc formato A4, con layout a moduli (tabella 1x2 per esercizio:
immagini a sinistra, testo a destra).
"""

from __future__ import annotations

import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

# Colore teal usato per i valori di ripetizioni/recupero.
COLORE_TEAL = {"red": 0.23, "green": 0.75, "blue": 0.70}

CREDENTIALS_PATH = "credentials.json"
SERVICE_ACCOUNT_PATH = "service_account.json"
TOKEN_PATH = "token.json"


class GoogleAuthError(Exception):
    """Sollevata quando l'autenticazione con le API Google non è configurata o fallisce."""


class GoogleDocsError(Exception):
    """Sollevata quando una chiamata alle API Google Docs/Drive fallisce."""


def get_credentials():
    """
    Restituisce le credenziali Google da usare per Docs/Drive.

    Modalità supportate:
      1. Service Account: se esiste 'service_account.json' viene usato direttamente
         (nessuna interazione utente necessaria, ma il documento apparterrà al SA).
      2. OAuth utente: usa/crea 'token.json' a partire da 'credentials.json',
         aprendo un flusso di autorizzazione nel browser se necessario.
    """
    if os.path.exists(SERVICE_ACCOUNT_PATH):
        return service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_PATH, scopes=SCOPES
        )

    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except (ValueError, OSError):
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            return creds
        except RefreshError:
            # Il refresh token non è più valido: eliminiamo il token e rifacciamo
            # da capo il flusso di autorizzazione interattivo.
            os.remove(TOKEN_PATH)
            creds = None

    if not os.path.exists(CREDENTIALS_PATH):
        raise GoogleAuthError(
            "File 'credentials.json' non trovato. Per configurare l'accesso a Google:\n"
            "1. Vai su https://console.cloud.google.com/ e crea (o seleziona) un progetto.\n"
            "2. Abilita le API 'Google Docs API' e 'Google Drive API'.\n"
            "3. Configura la schermata di consenso OAuth (tipo Esterno, aggiungendo il tuo "
            "account come utente di test se l'app non è pubblicata).\n"
            "4. Crea delle credenziali OAuth di tipo 'Applicazione desktop'.\n"
            "5. Scarica il file JSON generato e rinominalo 'credentials.json', posizionandolo "
            "nella cartella principale del progetto.\n"
            "In alternativa, per un uso senza interazione utente, puoi creare un Service Account "
            "e salvare la relativa chiave come 'service_account.json' (i documenti generati "
            "apparterranno però al Service Account e non al tuo account personale)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())
    return creds


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
        if stile:
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


def create_workout_document(
    exercises: list[dict],
    doc_title: str,
    docs_service=None,
    drive_service=None,
) -> dict:
    """
    Crea un Google Doc A4 verticale con un modulo per ogni esercizio (tabella
    1x2: immagini a sinistra, dettagli testuali a destra). Restituisce un
    dizionario con document_id e url del documento creato.

    docs_service e drive_service possono essere passati esplicitamente (utile
    per i test con mock); se omessi vengono costruiti a partire dalle
    credenziali restituite da get_credentials().
    """
    if docs_service is None or drive_service is None:
        creds = get_credentials()
        if docs_service is None:
            docs_service = build("docs", "v1", credentials=creds)
        if drive_service is None:
            drive_service = build("drive", "v3", credentials=creds)

    file_id_caricati: list[str] = []

    try:
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

        numero_esercizi = len(exercises)
        for indice, esercizio in enumerate(exercises):
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

            # 5. Ogni 3 esercizi (tranne dopo l'ultimo) inseriamo un'interruzione di pagina.
            e_multiplo_di_tre = (indice + 1) % 3 == 0
            e_ultimo = (indice + 1) == numero_esercizi
            if e_multiplo_di_tre and not e_ultimo:
                documento = docs_service.documents().get(documentId=doc_id).execute()
                indice_break = _indice_fine_documento(documento)
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {"insertPageBreak": {"location": {"index": indice_break}}}
                        ]
                    },
                ).execute()

        return {
            "document_id": doc_id,
            "url": f"https://docs.google.com/document/d/{doc_id}/edit",
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
