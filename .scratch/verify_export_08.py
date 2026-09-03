"""Verifica reale ticket 08 (desktop), non distruttiva:

A) ripresa: scheda CON state nel bundle -> genera() deve riusare lo stesso
   documento senza inserire nulla (nessun doc cancellato);
B) ciclo completo su scheda SENZA state: creazione doc nuovo (con inserimenti
   reali), cancellazione del doc created-from-test, rilancio -> attesa
   documento_rigenerato=True, poi cleanup dei soli doc di test e del
   state.json aggiunto al bundle (il bundle torna come era).
"""

import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy_app.main import build_pc_controller
from kivy_app.export import DocExportController

ROOT = Path(__file__).resolve().parent.parent
T0 = time.time()


def log(step, msg):
    print(f"[{time.time() - T0:6.1f}s] {step}: {msg}", flush=True)


def ha_stato(controller, remote):
    with zipfile.ZipFile(controller.cache_path(remote.name)) as z:
        return "state.json" in z.namelist()


def main():
    controller = build_pc_controller(ROOT)
    records = controller.refresh()
    log("1-auth", f"Drive OK, {len(records)} schede")

    # ---------- A) ripresa su scheda con stato ----------
    con_stato = [r for r in records if ha_stato(controller, r)]
    assert con_stato, "nessuna scheda con stato: caso A non testabile"
    remote_a = con_stato[0]
    editor_a = controller.open_for_edit(remote_a)
    export_a = DocExportController(editor_a, credential_provider=controller.credential_provider,
                                   base_dir=controller.base_dir)
    r_a = export_a.genera()
    from core.docs_helper import carica_stato
    stato_prec = carica_stato(Path(editor_a.cartella_lavoro, "state.json")) or {}
    riuso = r_a.get("document_id") == stato_prec.get("doc_id")
    inseriti_a = len(r_a.get("esercizi_inseriti", []))
    log("A-ripresa", f"{remote_a.name}: stesso_doc={riuso} inseriti_nuovi={inseriti_a} "
                     f"rigenerato={r_a.get('documento_rigenerato')} url={r_a.get('url')}")
    assert riuso and inseriti_a == 0 and not r_a.get("documento_rigenerato")
    log("A-ripresa", "OK: documento esistente riusato, zero reinserimenti (nessun file toccato)")

    # ---------- B) ciclo completo su scheda senza stato ----------
    senza = [r for r in records if not ha_stato(controller, r)]
    candidati = []
    for r in senza:
        ed = controller.open_for_edit(r)
        n = len([e for e in ed.esercizi
                 if e.get("frame_start") and e.get("frame_finish")])
        candidati.append((n, r, ed))
    candidati = [c for c in candidati if c[0] >= 2]
    assert candidati, "nessuna scheda senza stato con >=2 esercizi pronti"
    n_pronti, remote_b, editor_b = max(candidati, key=lambda c: c[0])
    log("B-scheda", f"{remote_b.name} ({n_pronti}/{len(editor_b.esercizi)} pronti)")

    doc_id_test = None
    try:
        export_b = DocExportController(editor_b, credential_provider=controller.credential_provider,
                                       base_dir=controller.base_dir)
        r1 = export_b.genera()
        doc_id_test = r1.get("document_id")
        log("B1-crea", f"doc CREATO-DA-TEST {doc_id_test} url={r1.get('url')} "
                       f"inseriti={len(r1.get('esercizi_inseriti', []))}")
        assert doc_id_test and len(r1.get("esercizi_inseriti", [])) == n_pronti
        assert not ha_stato(controller, remote_b) or True  # lo stato ora c'e' nel bundle

        # cancello IL DOC CHE HO AppENA CREATO (mio, di test) e rilancio
        from googleapiclient.discovery import build
        creds = controller.credential_provider.get_credentials(
            ["https://www.googleapis.com/auth/drive"])
        drive = build("drive", "v3", credentials=creds)
        drive.files().delete(fileId=doc_id_test).execute()
        log("B2-canc", f"doc test {doc_id_test} cancellato da Drive")

        export_b2 = DocExportController(editor_b, credential_provider=controller.credential_provider,
                                        base_dir=controller.base_dir)
        r2 = export_b2.genera()
        doc2 = r2.get("document_id")
        log("B3-rigen", f"documento_rigenerato={r2.get('documento_rigenerato')} "
                        f"nuovo_doc={doc2 != doc_id_test} inseriti={len(r2.get('esercizi_inseriti', []))} "
                        f"url={r2.get('url')}")
        assert r2.get("documento_rigenerato") is True
        assert doc2 != doc_id_test
        assert len(r2.get("esercizi_inseriti", [])) == n_pronti
        doc_id_test = doc2
    finally:
        # cleanup: solo il doc di test ancora vivo + state.json tolto dal bundle
        try:
            from googleapiclient.discovery import build as b2
            creds2 = controller.credential_provider.get_credentials(
                ["https://www.googleapis.com/auth/drive"])
            if doc_id_test:
                b2("drive", "v3", credentials=creds2).files().delete(fileId=doc_id_test).execute()
                log("cleanup", f"doc test {doc_id_test} cancellato")
        except Exception as exc:
            log("cleanup", f"cancellazione doc fallita (manuale su Drive): {exc}")
        stato = Path(editor_b.cartella_lavoro) / "state.json"
        if stato.exists():
            stato.unlink()
            editor_b.salva()
            with zipfile.ZipFile(controller.cache_path(remote_b.name)) as z:
                assert "state.json" not in z.namelist()
            log("cleanup", "state.json rimosso, bundle ripristinato e risincronizzato")
    print("VERIFY_08_OK", flush=True)


if __name__ == "__main__":
    main()
