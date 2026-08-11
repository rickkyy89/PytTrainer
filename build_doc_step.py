"""
Costruisce il documento in modo incrementale/resumibile: ogni invocazione fa
un solo passo (crea il documento la prima volta, poi aggiunge un esercizio
alla volta), cosi' da restare sotto i limiti di tempo di un singolo comando.
Stato persistito in state/doc_state.json.
"""
import json
import os
import sys

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import google_docs_helper as gdh
from csv_utils import parse_esercizi_csv

SCOPES = ["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive.file"]
DOC_STATE_PATH = "state/doc_state.json"
TITOLO = "SCHEDA 1: CORREZIONE POSTURALE E STABILITA"


def carica_esercizi_pronti():
    esercizi = parse_esercizi_csv("scheda.csv")
    pronti = []
    for i, e in enumerate(esercizi):
        with open(f"state/{i}.json", encoding="utf-8") as f:
            stato = json.load(f)
        if stato.get("frame_start") and stato.get("frame_finish"):
            e["frame_start"] = stato["frame_start"]
            e["frame_finish"] = stato["frame_finish"]
            pronti.append(e)
    return pronti


def carica_doc_state():
    if os.path.exists(DOC_STATE_PATH):
        with open(DOC_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"doc_id": None, "aggiunti": 0}


def salva_doc_state(stato):
    with open(DOC_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)


def get_services():
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    docs_service = gdh.build("docs", "v1", credentials=creds)
    drive_service = gdh.build("drive", "v3", credentials=creds)
    return docs_service, drive_service


def crea_documento(docs_service, doc_title):
    documento = docs_service.documents().create(body={"title": doc_title}).execute()
    doc_id = documento["documentId"]
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "updateDocumentStyle": {
                "documentStyle": {
                    "pageSize": {"width": gdh._dimensione_pt(595.28), "height": gdh._dimensione_pt(841.89)},
                    "marginTop": gdh._dimensione_pt(36), "marginBottom": gdh._dimensione_pt(36),
                    "marginLeft": gdh._dimensione_pt(36), "marginRight": gdh._dimensione_pt(36),
                },
                "fields": "pageSize,marginTop,marginBottom,marginLeft,marginRight",
            }
        }]},
    ).execute()
    titolo_testo = doc_title.upper() + "\n"
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [
            {"insertText": {"location": {"index": 1}, "text": titolo_testo}},
            gdh._richiesta_stile_testo(1, 1 + len(titolo_testo), {"bold": True, "size": 18}),
            {"updateParagraphStyle": {"range": {"startIndex": 1, "endIndex": 1 + len(titolo_testo)},
                                       "paragraphStyle": {"alignment": "CENTER"}, "fields": "alignment"}},
        ]},
    ).execute()
    return doc_id


def aggiungi_esercizio(docs_service, drive_service, doc_id, esercizio, indice, totale):
    start_id, uri_start = gdh.upload_image_to_drive(drive_service, esercizio["frame_start"])
    finish_id, uri_finish = gdh.upload_image_to_drive(drive_service, esercizio["frame_finish"])

    documento = docs_service.documents().get(documentId=doc_id).execute()
    indice_inserimento = gdh._indice_fine_documento(documento)
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertTable": {"rows": 1, "columns": 2, "location": {"index": indice_inserimento}}}]},
    ).execute()

    documento = docs_service.documents().get(documentId=doc_id).execute()
    elemento_tabella = gdh._trova_ultima_tabella(documento)
    celle = elemento_tabella["table"]["tableRows"][0]["tableCells"]
    left_start = celle[0]["content"][0]["startIndex"]
    right_start = celle[1]["content"][0]["startIndex"]

    richieste = gdh._richieste_cella_destra(right_start, esercizio)
    richieste += gdh._richieste_cella_sinistra(left_start, uri_start, uri_finish)
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": richieste}).execute()

    table_start = elemento_tabella["startIndex"]
    bordo = {"color": {"color": {"rgbColor": {"red": 0.92, "green": 0.92, "blue": 0.92}}},
             "width": gdh._dimensione_pt(0.5), "dashStyle": "SOLID"}
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [
            {"updateTableCellStyle": {"tableStartLocation": {"index": table_start}, "tableCellStyle": {
                "borderLeft": bordo, "borderRight": bordo, "borderTop": bordo, "borderBottom": bordo,
                "paddingLeft": gdh._dimensione_pt(4), "paddingRight": gdh._dimensione_pt(4),
                "paddingTop": gdh._dimensione_pt(4), "paddingBottom": gdh._dimensione_pt(4)},
                "fields": "borderLeft,borderRight,borderTop,borderBottom,paddingLeft,paddingRight,paddingTop,paddingBottom"}},
            {"updateTableColumnProperties": {"tableStartLocation": {"index": table_start}, "columnIndices": [0],
                "tableColumnProperties": {"width": gdh._dimensione_pt(220), "widthType": "FIXED_WIDTH"}, "fields": "width,widthType"}},
            {"updateTableColumnProperties": {"tableStartLocation": {"index": table_start}, "columnIndices": [1],
                "tableColumnProperties": {"width": gdh._dimensione_pt(300), "widthType": "FIXED_WIDTH"}, "fields": "width,widthType"}},
        ]},
    ).execute()

    e_multiplo_di_tre = (indice + 1) % 3 == 0
    e_ultimo = (indice + 1) == totale
    if e_multiplo_di_tre and not e_ultimo:
        documento = docs_service.documents().get(documentId=doc_id).execute()
        indice_break = gdh._indice_fine_documento(documento)
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": [{"insertPageBreak": {"location": {"index": indice_break}}}]},
        ).execute()

    gdh.delete_drive_file(drive_service, start_id)
    gdh.delete_drive_file(drive_service, finish_id)


def main():
    pronti = carica_esercizi_pronti()
    stato = carica_doc_state()
    docs_service, drive_service = get_services()

    if stato["doc_id"] is None:
        doc_id = crea_documento(docs_service, TITOLO)
        stato["doc_id"] = doc_id
        salva_doc_state(stato)
        print("Documento creato:", doc_id)
        return

    if stato["aggiunti"] >= len(pronti):
        print("Documento gia' completo:", stato["doc_id"])
        print("URL:", f"https://docs.google.com/document/d/{stato['doc_id']}/edit")
        return

    i = stato["aggiunti"]
    esercizio = pronti[i]
    print(f"Aggiungo esercizio {i+1}/{len(pronti)}: {esercizio['nome']}")
    aggiungi_esercizio(docs_service, drive_service, stato["doc_id"], esercizio, i, len(pronti))
    stato["aggiunti"] = i + 1
    salva_doc_state(stato)
    print("Fatto.")
    if stato["aggiunti"] >= len(pronti):
        print("URL:", f"https://docs.google.com/document/d/{stato['doc_id']}/edit")


if __name__ == "__main__":
    main()
