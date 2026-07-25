"""
Test di compatibilità: un file .scheda creato con la VECCHIA versione basata
su pandas (parse_esercizi_csv/scrivi_esercizi_csv implementate con
pandas.read_csv/to_csv) deve continuare ad aprirsi con l'implementazione
attuale basata sul modulo 'csv' della libreria standard.

Il manifest viene qui costruito a mano (non con csv_utils) per riprodurre
fedelmente l'output tipico di pandas.to_csv: intestazione con le 11 colonne,
valori con virgole e virgolette che richiedono il quoting RFC4180, un
timestamp non intero (12.5) e celle vuote per le colonne opzionali assenti.
Serve a garantire che i .scheda già esistenti degli utenti (prodotti prima
del refactor "addio pandas") continuino ad aprirsi senza richiedere una
riconversione manuale.
"""

import os
import sys
import zipfile
from pathlib import Path

RADICE_PROGETTO = Path(__file__).resolve().parent.parent
if str(RADICE_PROGETTO) not in sys.path:
    sys.path.insert(0, str(RADICE_PROGETTO))

from scheda_file import NOME_MANIFEST, carica_scheda, salva_scheda  # noqa: E402

# Manifest nel formato tipico prodotto dalla vecchia scrivi_esercizi_csv()
# basata su pandas.DataFrame.to_csv(index=False): quoting RFC4180 minimale
# (solo dove serve: virgole e virgolette nei campi), celle vuote per le
# colonne opzionali non valorizzate, TimestampStart non intero (12.5).
_MANIFEST_STILE_PANDAS = (
    "Nome,Spiegazione,Note,Ripetizioni,Recupero,Gruppo,VideoURL,"
    "TimestampStart,TimestampFinish,FrameStartPath,FrameFinishPath\n"
    '"Squat, Front",Scendi e risali,"Scendi ""lentamente"" e risali",3x12,90 SEC,,'
    "https://youtu.be/abc123,12.5,,frames/squat_front_start.jpg,\n"
    "Plank,Mantieni la posizione,,1x60s,60 SEC,,,,,,\n"
)

_FRAME_FINTO = b"\xff\xd8\xff\xe0vecchio_frame_squat_front_start"


def _crea_bundle_stile_pandas(percorso) -> None:
    """Costruisce a mano un .scheda con il manifest 'vecchio stile pandas' più
    un frame finto in frames/, senza passare da salva_scheda()/csv_utils."""
    with zipfile.ZipFile(percorso, "w", zipfile.ZIP_DEFLATED) as archivio:
        archivio.writestr(NOME_MANIFEST, _MANIFEST_STILE_PANDAS)
        archivio.writestr("frames/squat_front_start.jpg", _FRAME_FINTO)


def test_carica_scheda_bundle_vecchio_stile_pandas(tmp_path):
    percorso_bundle = tmp_path / "vecchia_scheda.scheda"
    _crea_bundle_stile_pandas(percorso_bundle)

    esercizi, cartella_lavoro = carica_scheda(str(percorso_bundle))

    assert len(esercizi) == 2
    squat, plank = esercizi

    # Riga con virgola nel nome e virgolette nella nota: il parsing RFC4180
    # deve restituire i valori "srotolati" (senza le virgolette di escape).
    assert squat["nome"] == "Squat, Front"
    assert squat["spiegazione"] == "Scendi e risali"
    assert squat["note"] == 'Scendi "lentamente" e risali'
    assert squat["ripetizioni"] == "3x12"
    assert squat["recupero"] == "90 SEC"
    assert squat["gruppo"] == ""
    assert squat["video_url"] == "https://youtu.be/abc123"
    assert squat["ts_start"] == 12.5
    assert isinstance(squat["ts_start"], float)
    # Cella vuota -> None, non 0: distinzione fondamentale per l'euristica
    # 10%/50% a valle (un timestamp esplicito a 0 sarebbe legittimo).
    assert squat["ts_finish"] is None
    assert squat["frame_start"] is not None
    assert squat["frame_start"].endswith("squat_front_start.jpg")
    assert os.path.exists(squat["frame_start"])
    with open(squat["frame_start"], "rb") as file_frame:
        assert file_frame.read() == _FRAME_FINTO
    # Il frame finish non è nell'archivio: la chiave torna a None (verrà
    # ri-estratta a valle da scegli_ed_estrai).
    assert squat["frame_finish"] is None

    assert plank["nome"] == "Plank"
    assert plank["note"] == ""
    assert plank["gruppo"] == ""
    assert plank["video_url"] == ""
    assert plank["ts_start"] is None
    assert plank["ts_finish"] is None
    assert plank["frame_start"] is None
    assert plank["frame_finish"] is None


def test_salva_scheda_dopo_ricarica_bundle_vecchio_e_ricaricabile_identico(tmp_path):
    """Ricaricare un bundle vecchio stile e risalvarlo con salva_scheda() deve
    produrre un bundle a sua volta ricaricabile, con gli stessi valori."""
    percorso_bundle_vecchio = tmp_path / "vecchia_scheda.scheda"
    _crea_bundle_stile_pandas(percorso_bundle_vecchio)

    esercizi, _ = carica_scheda(str(percorso_bundle_vecchio))

    percorso_bundle_nuovo = tmp_path / "risalvata.scheda"
    salva_scheda(esercizi, str(percorso_bundle_nuovo))

    esercizi_ricaricati, _ = carica_scheda(
        str(percorso_bundle_nuovo), str(tmp_path / "risalvata_altra_cache.work")
    )

    assert len(esercizi_ricaricati) == len(esercizi) == 2
    for originale, ricaricato in zip(esercizi, esercizi_ricaricati):
        assert ricaricato["nome"] == originale["nome"]
        assert ricaricato["spiegazione"] == originale["spiegazione"]
        assert ricaricato["note"] == originale["note"]
        assert ricaricato["ripetizioni"] == originale["ripetizioni"]
        assert ricaricato["recupero"] == originale["recupero"]
        assert ricaricato["gruppo"] == originale["gruppo"]
        assert ricaricato["video_url"] == originale["video_url"]
        assert ricaricato["ts_start"] == originale["ts_start"]
        assert ricaricato["ts_finish"] == originale["ts_finish"]
        # I frame esistenti su disco al momento del salva_scheda() vengono
        # reimballati: quello di Squat deve sopravvivere al round-trip con
        # contenuto identico; Plank (senza frame) resta senza frame.
        if originale["frame_start"] is not None:
            assert ricaricato["frame_start"] is not None
            with open(originale["frame_start"], "rb") as file_originale, open(
                ricaricato["frame_start"], "rb"
            ) as file_ricaricato:
                assert file_originale.read() == file_ricaricato.read()
        else:
            assert ricaricato["frame_start"] is None
        assert ricaricato["frame_finish"] is None
