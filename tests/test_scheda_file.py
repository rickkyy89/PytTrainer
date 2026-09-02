"""
Test del file scheda unico (.scheda): archivio zip con manifest CSV, frame e
stato di ripresa del Google Doc. Come per test_smoke.py non serve rete né
credenziali: i frame sono file fittizi con magic number JPEG.
"""

import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

RADICE_PROGETTO = Path(__file__).resolve().parent.parent
if str(RADICE_PROGETTO) not in sys.path:
    sys.path.insert(0, str(RADICE_PROGETTO))

from core import scheda_file  # noqa: E402
from core.csv_utils import parse_esercizi_csv, slugify  # noqa: E402
from core.scheda_file import (  # noqa: E402
    CARTELLA_FRAMES,
    NOME_MANIFEST,
    NOME_STATO,
    SchedaFileError,
    carica_scheda,
    carica_scheda_da_file_like,
    cartella_frames,
    cartella_lavoro_per_bundle,
    percorso_stato,
    salva_scheda,
    scheda_bytes,
    titolo_scheda,
)


def test_import_modulo_scheda_file():
    """Le funzioni pubbliche del modulo devono esistere."""
    for nome in (
        "carica_scheda",
        "carica_scheda_da_file_like",
        "salva_scheda",
        "scheda_bytes",
        "cartella_lavoro_per_bundle",
        "cartella_frames",
        "percorso_stato",
        "SchedaFileError",
    ):
        assert hasattr(scheda_file, nome)


def _crea_esercizio_con_frame(nome, cartella, con_frame=True):
    """Esercizio di prova con frame JPEG fittizi già su disco in 'cartella'."""
    esercizio = {
        "nome": nome,
        "spiegazione": "Spiegazione di prova per il test.",
        "note": "Nota di prova.",
        "ripetizioni": "3x10",
        "recupero": "60 SEC",
        "gruppo": "",
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "ts_start": 5.0,
        "ts_finish": 20.0,
        "frame_start": None,
        "frame_finish": None,
    }
    if con_frame:
        slug = slugify(nome)
        percorso_start = Path(cartella) / f"{slug}_start.jpg"
        percorso_finish = Path(cartella) / f"{slug}_finish.jpg"
        percorso_start.write_bytes(b"\xff\xd8\xff\xe0finto_jpeg_start")
        percorso_finish.write_bytes(b"\xff\xd8\xff\xe0finto_jpeg_finish")
        esercizio["frame_start"] = str(percorso_start)
        esercizio["frame_finish"] = str(percorso_finish)
    return esercizio


def test_salva_e_carica_scheda_round_trip(tmp_path):
    esercizi = [
        _crea_esercizio_con_frame("Squat Bulgaro", tmp_path),
        _crea_esercizio_con_frame("Hip Thrust", tmp_path),
    ]
    percorso_bundle = str(tmp_path / "mia_scheda.scheda")
    percorso_json_stato = tmp_path / "stato_di_prova.json"
    percorso_json_stato.write_text(
        json.dumps({"doc_id": "doc123", "titolo": "Scheda Test", "esercizi": []}),
        encoding="utf-8",
    )

    salva_scheda(esercizi, percorso_bundle, state_path=str(percorso_json_stato))

    with zipfile.ZipFile(percorso_bundle) as archivio:
        membri = set(archivio.namelist())
    assert membri == {
        NOME_MANIFEST,
        NOME_STATO,
        f"{CARTELLA_FRAMES}/squat_bulgaro_start.jpg",
        f"{CARTELLA_FRAMES}/squat_bulgaro_finish.jpg",
        f"{CARTELLA_FRAMES}/hip_thrust_start.jpg",
        f"{CARTELLA_FRAMES}/hip_thrust_finish.jpg",
    }

    # Il caricamento avviene in una cartella di lavoro diversa da quella dei
    # frame originali: i percorsi devono puntare ai file estratti.
    cartella_lavoro = str(tmp_path / "altra_cache.work")
    caricati, lavoro_effettiva = carica_scheda(percorso_bundle, cartella_lavoro)
    assert lavoro_effettiva == cartella_lavoro
    assert [e["nome"] for e in caricati] == ["Squat Bulgaro", "Hip Thrust"]
    for originale, caricato in zip(esercizi, caricati):
        assert caricato["video_url"] == originale["video_url"]
        assert caricato["ts_start"] == originale["ts_start"]
        assert caricato["ts_finish"] == originale["ts_finish"]
        for chiave in ("frame_start", "frame_finish"):
            assert caricato[chiave] is not None
            assert caricato[chiave].startswith(cartella_lavoro)
            assert os.path.exists(caricato[chiave])
            with open(caricato[chiave], "rb") as file_frame:
                assert file_frame.read() == Path(originale[chiave]).read_bytes()

    # Lo state.json del bundle deve essere stato estratto nella cache.
    assert json.loads(Path(percorso_stato(cartella_lavoro)).read_text(encoding="utf-8"))[
        "doc_id"
    ] == "doc123"


def test_manifest_nel_bundle_ha_percorsi_relativi(tmp_path):
    esercizi = [_crea_esercizio_con_frame("Affondi", tmp_path)]
    percorso_bundle = str(tmp_path / "scheda.scheda")
    salva_scheda(esercizi, percorso_bundle)

    with zipfile.ZipFile(percorso_bundle) as archivio:
        righe_manifest = parse_esercizi_csv(io.BytesIO(archivio.read(NOME_MANIFEST)))
    assert righe_manifest[0]["frame_start"] == f"{CARTELLA_FRAMES}/affondi_start.jpg"
    assert righe_manifest[0]["frame_finish"] == f"{CARTELLA_FRAMES}/affondi_finish.jpg"


def test_salva_e_carica_titolo_scheda(tmp_path):
    percorso_bundle = str(tmp_path / "scheda.scheda")
    lavoro = str(tmp_path / "scheda.scheda.work")

    salva_scheda([], percorso_bundle, titolo="Scheda Forza - Settembre")
    carica_scheda(percorso_bundle, lavoro)

    assert titolo_scheda(lavoro) == "Scheda Forza - Settembre"


def test_salva_scheda_frame_mancante_su_disco(tmp_path):
    """Un frame referenziato ma inesistente su disco produce cella vuota, non errori."""
    esercizio = _crea_esercizio_con_frame("Plank", tmp_path, con_frame=False)
    esercizio["frame_start"] = str(tmp_path / "inesistente_start.jpg")
    esercizio["frame_finish"] = str(tmp_path / "inesistente_finish.jpg")
    percorso_bundle = str(tmp_path / "scheda.scheda")

    salva_scheda([esercizio], percorso_bundle)

    with zipfile.ZipFile(percorso_bundle) as archivio:
        assert archivio.namelist() == [NOME_MANIFEST]
        righe = parse_esercizi_csv(io.BytesIO(archivio.read(NOME_MANIFEST)))
    assert righe[0]["frame_start"] is None
    assert righe[0]["frame_finish"] is None


def test_salva_scheda_include_backup_pre_ritaglio(tmp_path):
    esercizio = _crea_esercizio_con_frame("Squat", tmp_path)
    percorso_backup = tmp_path / "squat_start_orig.jpg"
    percorso_backup.write_bytes(b"\xff\xd8\xff\xe0finto_jpeg_originale")
    percorso_bundle = str(tmp_path / "scheda.scheda")

    salva_scheda([esercizio], percorso_bundle)

    with zipfile.ZipFile(percorso_bundle) as archivio:
        assert f"{CARTELLA_FRAMES}/squat_start_orig.jpg" in archivio.namelist()


def test_salva_scheda_backup_segue_frame_rinominato_per_collisione(tmp_path):
    """Il backup del secondo frame omonimo deve restare ripristinabile dopo il load."""
    prima = _crea_esercizio_con_frame("Squat", tmp_path)
    altra_cartella = tmp_path / "altra_cartella"
    altra_cartella.mkdir()
    seconda = _crea_esercizio_con_frame("Squat", altra_cartella)
    Path(seconda["frame_start"]).with_name("squat_start_orig.jpg").write_bytes(b"backup_secondo")
    percorso_bundle = str(tmp_path / "duplicati.scheda")

    salva_scheda([prima, seconda], percorso_bundle)

    with zipfile.ZipFile(percorso_bundle) as archivio:
        assert f"{CARTELLA_FRAMES}/squat_start_2.jpg" in archivio.namelist()
        assert f"{CARTELLA_FRAMES}/squat_start_2_orig.jpg" in archivio.namelist()

    caricati, _ = carica_scheda(percorso_bundle, str(tmp_path / "duplicati.work"))
    backup_secondo = Path(caricati[1]["frame_start"]).with_name("squat_start_2_orig.jpg")
    assert backup_secondo.read_bytes() == b"backup_secondo"


def test_carica_scheda_frame_referenziato_ma_assente_dallo_zip(tmp_path):
    """Manifest che punta a frame non inclusi nell'archivio (o con percorsi
    legacy assoluti): le chiavi frame tornano a None per la ri-estrazione."""
    manifest = (
        "Nome,Spiegazione,Note,Ripetizioni,Recupero,Gruppo,VideoURL,"
        "TimestampStart,TimestampFinish,FrameStartPath,FrameFinishPath\n"
        "Squat,Spiegazione,Note,3x12,90 SEC,,,,,frames/squat_start.jpg,/vecchio/percorso/assoluto_finish.jpg\n"
    )
    percorso_bundle = tmp_path / "scheda.scheda"
    with zipfile.ZipFile(percorso_bundle, "w") as archivio:
        archivio.writestr(NOME_MANIFEST, manifest)

    caricati, _ = carica_scheda(str(percorso_bundle))
    assert caricati[0]["frame_start"] is None
    assert caricati[0]["frame_finish"] is None


def test_scheda_bytes_ricaricabile_da_file_like(tmp_path):
    esercizi = [_crea_esercizio_con_frame("Ponte Glutei", tmp_path)]
    contenuto = scheda_bytes(esercizi)

    cartella_lavoro = str(tmp_path / "cache.work")
    caricati = carica_scheda_da_file_like(io.BytesIO(contenuto), cartella_lavoro)
    assert caricati[0]["nome"] == "Ponte Glutei"
    assert os.path.exists(caricati[0]["frame_start"])
    assert os.path.exists(caricati[0]["frame_finish"])


def test_salva_scheda_sovrascrittura_atomica(tmp_path):
    percorso_bundle = str(tmp_path / "scheda.scheda")
    esercizi = [_crea_esercizio_con_frame("Squat", tmp_path)]
    salva_scheda(esercizi, percorso_bundle)
    salva_scheda(esercizi + [_crea_esercizio_con_frame("Affondi", tmp_path)], percorso_bundle)

    with zipfile.ZipFile(percorso_bundle) as archivio:
        righe = parse_esercizi_csv(io.BytesIO(archivio.read(NOME_MANIFEST)))
    assert [riga["nome"] for riga in righe] == ["Squat", "Affondi"]
    assert not os.path.exists(f"{percorso_bundle}.tmp")


def test_carica_scheda_zip_slip_rifiutato(tmp_path):
    percorso_bundle = tmp_path / "malevola.scheda"
    with zipfile.ZipFile(percorso_bundle, "w") as archivio:
        archivio.writestr(NOME_MANIFEST, "Nome,Spiegazione,Note,Ripetizioni,Recupero\n")
        archivio.writestr("frames/../evil.jpg", b"payload")

    cartella_lavoro = tmp_path / "cache.work"
    with pytest.raises(SchedaFileError):
        carica_scheda(str(percorso_bundle), str(cartella_lavoro))
    assert not (tmp_path / "evil.jpg").exists()


def test_carica_scheda_errori_espliciti(tmp_path):
    # File inesistente.
    with pytest.raises(SchedaFileError):
        carica_scheda(str(tmp_path / "non_esiste.scheda"))

    # Non è uno zip.
    percorso_falso = tmp_path / "falsa.scheda"
    percorso_falso.write_bytes(b"questo non e' uno zip")
    with pytest.raises(SchedaFileError):
        carica_scheda(str(percorso_falso))

    # Zip valido ma senza manifest.
    percorso_senza_manifest = tmp_path / "vuota.scheda"
    with zipfile.ZipFile(percorso_senza_manifest, "w") as archivio:
        archivio.writestr("frames/x.jpg", b"\xff\xd8\xff\xe0")
    with pytest.raises(SchedaFileError):
        carica_scheda(str(percorso_senza_manifest))


def test_carica_scheda_senza_stato_rimuove_stato_stantio(tmp_path):
    """Se il bundle non contiene state.json, un eventuale stato rimasto nella
    cache di una run precedente non deve sopravvivere (il bundle vince)."""
    percorso_bundle = str(tmp_path / "scheda.scheda")
    cartella_lavoro = cartella_lavoro_per_bundle(percorso_bundle)
    stato_stantio = Path(percorso_stato(cartella_lavoro))
    stato_stantio.write_text(json.dumps({"doc_id": "vecchio"}), encoding="utf-8")

    salva_scheda([_crea_esercizio_con_frame("Squat", tmp_path)], percorso_bundle)
    carica_scheda(percorso_bundle)
    assert not stato_stantio.exists()


def test_scheda_vuota_round_trip(tmp_path):
    percorso_bundle = str(tmp_path / "vuota.scheda")
    salva_scheda([], percorso_bundle)
    caricati, _ = carica_scheda(percorso_bundle)
    assert caricati == []


def test_cartella_frames_e_percorso_stato(tmp_path):
    cartella_lavoro = str(tmp_path / "scheda.scheda.work")
    percorso_frames = cartella_frames(cartella_lavoro)
    assert percorso_frames == os.path.join(cartella_lavoro, CARTELLA_FRAMES)
    assert os.path.isdir(percorso_frames)
    assert percorso_stato(cartella_lavoro) == os.path.join(cartella_lavoro, NOME_STATO)
    assert cartella_lavoro_per_bundle("x/y/scheda.scheda") == "x/y/scheda.scheda.work"


def test_cartella_lavoro_per_bundle_usa_base_dir_esplicita(tmp_path):
    base_dir = tmp_path / "cache"
    assert cartella_lavoro_per_bundle("C:/schede/scheda.scheda", base_dir=base_dir) == (
        "C:/schede/scheda.scheda.work"
    )


def test_bundle_relativo_con_base_dir_non_dipende_dalla_cwd(tmp_path, monkeypatch):
    base_dir = tmp_path / "schede"
    base_dir.mkdir()
    (base_dir / "archivio").mkdir()
    esercizi = [_crea_esercizio_con_frame("Squat", tmp_path)]

    monkeypatch.chdir(tmp_path)
    salva_scheda(esercizi, "archivio/scheda.scheda", base_dir=base_dir)

    percorso_bundle = base_dir / "archivio" / "scheda.scheda"
    assert percorso_bundle.exists()

    altra_cwd = tmp_path / "altra_cwd"
    altra_cwd.mkdir()
    monkeypatch.chdir(altra_cwd)
    caricati, lavoro = carica_scheda("archivio/scheda.scheda", base_dir=base_dir)

    assert caricati[0]["nome"] == "Squat"
    assert os.path.normpath(lavoro) == os.path.normpath(str(percorso_bundle) + ".work")
    assert Path(caricati[0]["frame_start"]).is_file()
