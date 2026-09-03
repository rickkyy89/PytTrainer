"""Verifica ticket 10 su Drive reale con tre 'dispositivi' (cache separate)
su una scheda di test creata e distrutta dallo script.

Round 1: conflitto al SALVATAGGIO (editor.salva -> SyncConflict, nessun
         upload) -> scelta "locale" (upload forzato: remoto = versione B).
Round 2: conflitto in corso rilevato anche dal check all'APERTURA
         (check_conflict senza download) -> scelta "remota" (cache = remoto,
         modifiche B scartate).
Round 3: nuovo conflitto -> scelta "duplicata" (copia suffissata "(2)" con la
         versione B, originale riallineato alla versione A).
Cleanup: eliminazione delle schedine di test da Drive e delle cache locali.
"""

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.drive_sync import SyncConflict, UploadResult
from core.platform import LocalCredentialsProvider
from core.scheda_file import carica_scheda
from kivy_app.config import FolderConfigStore
from kivy_app.controller import DriveHomeController

ROOT = Path(__file__).resolve().parent.parent
NOME_TEST = "TEST VERIFICA 10.scheda"
T0 = time.time()
CONTATORE = iter(range(1000, 9999))


def log(step, msg):
    print(f"[{time.time() - T0:6.1f}s] {step}: {msg}", flush=True)


def make_dev(dev):
    d = ROOT / ".scratch" / f"dev10-{dev}"
    d.mkdir(parents=True, exist_ok=True)
    provider = LocalCredentialsProvider(ROOT)

    def dsf(creds):
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds)

    return DriveHomeController(
        FolderConfigStore(d / "drive-folders.json"), d / "drive-cache",
        credential_provider=provider, drive_service_factory=dsf, base_dir=ROOT)


def cerca(controller, nome=NOME_TEST):
    for r in controller.refresh():
        if r.name == nome:
            return r
    raise AssertionError(f"scheda {nome!r} non trovata su Drive")


def esercizio_nome(controller, remote):
    """Nome del primo esercizio: scarica la versione remota piu' recente."""
    scheda = controller.open(remote)
    return scheda.exercises[0].name if scheda.exercises else "(nessun esercizio)"


def nome_in_cache(controller, remote):
    """Nome del primo esercizio leggendo SOLO il bundle nella cache locale."""
    esercizi, _ = carica_scheda(str(controller.cache_path(remote.name)), base_dir=ROOT)
    return esercizi[0]["nome"] if esercizi else "(nessun esercizio)"


def prepara_esercizio(editor, nome):
    idx = editor.aggiungi() if not editor.esercizi else 0
    editor.aggiorna(idx, nome=nome, ripetizioni="1x1", recupero="10 SEC",
                    spiegazione="test", note="")
    return editor.salva()


def nuova_modifica_a(a, nome):
    time.sleep(2)  # timestamp Drive distinti fra upload ravvicinati
    assert isinstance(prepara_esercizio(a.open_for_edit(cerca(a)), nome), UploadResult)
    log("A", f"caricata {nome!r}")


def conflitto_al_salvataggio(b, ed_b):
    """B modifica e salva: SyncConflict senza upload (mai last-write-wins)."""
    nome_b = f"B-{next(CONTATORE)}"
    conflitto = prepara_esercizio(ed_b, nome_b)
    assert isinstance(conflitto, SyncConflict), f"atteso SyncConflict, arrivato {conflitto!r}"
    return nome_b, conflitto


def main():
    a = make_dev("a")
    b = make_dev("b")
    c = make_dev("c")

    # idempotenza: se una esecuzione precedente e' morta a meta', rimuovi i residui
    for r in a.refresh():
        if r.name.startswith("TEST VERIFICA 10"):
            a.delete(r)
            log("pre-cleanup", f"rimosso residuo {r.name}")
    for dev in ("a", "b", "c"):
        shutil.rmtree(ROOT / ".scratch" / f"dev10-{dev}", ignore_errors=True)
    a = make_dev("a")

    remote = a.create(NOME_TEST)
    assert isinstance(prepara_esercizio(a.open_for_edit(remote), "A-init"), UploadResult)
    log("setup", f"creata {NOME_TEST}")

    # ============ Round 1: conflitto al salvataggio -> "locale"
    ed_b = b.open_for_edit(cerca(b))          # B sincronizza su A-init
    nuova_modifica_a(a, "A-mod1")             # remoto piu' recente per B
    nome_b1, conflitto1 = conflitto_al_salvataggio(b, ed_b)
    assert conflitto1.local_modified_time and conflitto1.remote_modified_time
    esito = b.resolve_conflict(conflitto1, choice="locale",
                               local_path=ed_b.percorso_bundle)
    assert isinstance(esito, UploadResult), esito
    time.sleep(1)
    assert esercizio_nome(c, cerca(c)) == nome_b1
    log("R1", f"OK 'locale': remoto forzato alla versione B ({nome_b1!r})")

    # ============ Round 2: conflitto in corso -> check all'apertura -> "remota"
    ed_b = b.open_for_edit(cerca(b))          # B riparte dalla sua B-mod (syncata)
    nuova_modifica_a(a, "A-mod2")             # remoto di nuovo piu' recente
    nome_b2, conflitto2 = conflitto_al_salvataggio(b, ed_b)  # salva -> conflitto
    conflitto_ap = b.check_conflict(cerca(b))  # anche il check di apertura lo vede
    assert conflitto_ap is not None, "il check all'apertura non vede il conflitto"
    log("R2", "OK: check_conflict (apertura) rileva il conflitto senza download")
    esito = b.resolve_conflict(conflitto2, choice="remota",
                               local_path=ed_b.percorso_bundle)
    time.sleep(1)
    assert nome_in_cache(b, cerca(b)) == "A-mod2", "cache B non riallineata al remoto"
    assert b.check_conflict(cerca(b)) is None, "il conflitto non si e' chiuso"
    log("R2", f"OK 'remota': locale {nome_b2!r} scartata, cache B == A-mod2")

    # ============ Round 3: "duplicata"
    ed_b = b.open_for_edit(cerca(b))          # B allineata ad A-mod2
    nuova_modifica_a(a, "A-mod3")
    nome_b3, conflitto3 = conflitto_al_salvataggio(b, ed_b)
    esito = b.resolve_conflict(conflitto3, choice="duplicata",
                               local_path=ed_b.percorso_bundle)
    assert isinstance(esito, UploadResult), esito
    assert esito.remote.name == "TEST VERIFICA 10 (2).scheda", esito.remote.name
    dup = cerca(c, esito.remote.name)
    time.sleep(1)
    assert esercizio_nome(c, dup) == nome_b3, "il duplicato non porta la versione B"
    assert nome_in_cache(b, cerca(b)) == "A-mod3", "l'originale non e' riallineato"
    assert b.check_conflict(cerca(b)) is None, "duplicata deve chiudere il conflitto"
    log("R3", f"OK 'duplicata': {dup.name} con {nome_b3!r}, originale = A-mod3")

    # ============ cleanup
    for nome in (NOME_TEST, esito.remote.name):
        try:
            c.delete(cerca(c, nome))
        except Exception as exc:
            log("cleanup", f"eliminazione {nome} fallita (manuale su Drive): {exc}")
    for dev in ("a", "b", "c"):
        shutil.rmtree(ROOT / ".scratch" / f"dev10-{dev}", ignore_errors=True)
    log("cleanup", "schedine di test eliminate da Drive, cache locali rimosse")
    print("VERIFY_10_OK", flush=True)


if __name__ == "__main__":
    main()
