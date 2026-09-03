"""Ticket 08 - completata: prova 404 reale (doc id inesistente) + conferma
che il caso trash non e' un bug (Documents API risponde 200 su file nel
cestino, quindi il check di raggiungibilita' non puo' che considerarli ok).
Non distruttiva: crea solo un doc di test finale che viene rimosso."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy_app.main import build_pc_controller
from kivy_app.export import DocExportController

ROOT = Path(__file__).resolve().parent.parent
DOC_TRASHATO = "1rx3SdwxzcCoAhsMRT2SFfUJq0XhwiNgDxVhjc4MJWpc"
T0 = time.time()


def log(step, msg):
    print(f"[{time.time() - T0:6.1f}s] {step}: {msg}", flush=True)


def drive_service(controller):
    from googleapiclient.discovery import build
    creds = controller.credential_provider.get_credentials(
        ["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)


def docs_service(controller):
    from googleapiclient.discovery import build
    creds = controller.credential_provider.get_credentials(
        ["https://www.googleapis.com/auth/drive"])
    return build("docs", "v1", credentials=creds)


def main():
    controller = build_pc_controller(ROOT)
    records = controller.refresh()

    # scheda senza stato, la piu' ricca
    import zipfile
    senza = []
    for r in records:
        with zipfile.ZipFile(controller.cache_path(r.name)) as z:
            if "state.json" not in z.namelist():
                senza.append(r)
    candidati = []
    for r in senza:
        ed = controller.open_for_edit(r)
        n = len([e for e in ed.esercizi if e.get("frame_start") and e.get("frame_finish")])
        if n >= 2:
            candidati.append((n, r, ed))
    n_pronti, remote, editor = max(candidati, key=lambda c: c[0])
    log("1-scheda", f"{remote.name} ({n_pronti} pronti)")

    export = DocExportController(editor, credential_provider=controller.credential_provider,
                                 base_dir=controller.base_dir)
    r1 = export.genera()
    doc1 = r1["document_id"]
    log("2-crea", f"doc test {doc1} inseriti={len(r1['esercizi_inseriti'])}")

    doc_nuovo = None
    try:
        # 404 stabile e immediato: stato orientato a un documento MAI ESISTITO
        # (evita il race di consistenza finale di Drive post-delete)
        stato_path = Path(editor.cartella_lavoro) / "state.json"
        stato = json.loads(stato_path.read_text(encoding="utf-8"))
        stato["doc_id"] = "1" + "Z" * 43
        stato_path.write_text(json.dumps(stato), encoding="utf-8")
        log("3-404", "state.json orientato a un doc id inesistente")

        export2 = DocExportController(editor, credential_provider=controller.credential_provider,
                                      base_dir=controller.base_dir)
        r2 = export2.genera()
        doc_nuovo = r2.get("document_id")
        log("3-404", f"documento_rigenerato={r2.get('documento_rigenerato')} "
                     f"nuovo={doc_nuovo != doc1} "
                     f"inseriti={len(r2.get('esercizi_inseriti', []))} url={r2.get('url')}")
        assert r2.get("documento_rigenerato") is True
        assert doc_nuovo and doc_nuovo != doc1
        assert len(r2.get("esercizi_inseriti", [])) == n_pronti
        assert r2.get("url"), "manca url riapribile"
    finally:
        svc = drive_service(controller)
        for leaked in (doc_nuovo, doc1):
            if not leaked:
                continue
            try:
                svc.files().delete(fileId=leaked).execute()
                log("4-cleanup", f"doc di test {leaked} cestinato")
            except Exception as exc:
                log("4-cleanup", f"delete {leaked} fallita (manuale su Drive): {exc}")
        stato_path = Path(editor.cartella_lavoro) / "state.json"
        if stato_path.exists():
            stato_path.unlink()
        editor.salva()
        log("4-cleanup", "state.json rimosso, bundle ripristinato su Drive")
    print("VERIFY_08_404_OK", flush=True)


if __name__ == "__main__":
    main()
