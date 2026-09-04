"""Ticket 07 flow tests: extractor backend seam, media controller, Android MMR."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_helper import FrameExtractionError, VideoSearchError, extract_frame
from kivy_app.media import (
    MediaFlowController,
    MediaFlowError,
    url_con_inizio,
    percorso_backup_frame,
)
from kivy_app.editor import SchedaEditorController
from kivy_app.platform_android import AndroidFrameExtractor


# ------------------------------------------------------- core seam (extract)

class FakeExtractorBackend:
    def __init__(self, produce=True):
        self.calls = []
        self.produce = produce

    def extract(self, stream_url, ts, out_path, headers=None):
        self.calls.append((stream_url, ts, out_path, headers))
        if self.produce:
            Path(out_path).write_bytes(b"\xff\xd8\xff\xe0jpeg")


def test_extract_frame_usa_il_backend_extractor_e_salta_ffmpeg(tmp_path):
    backend = FakeExtractorBackend()
    out = tmp_path / "f.jpg"

    percorso = extract_frame("https://stream", 12.5, str(out), {"Range": "x"},
                             ffmpeg_backend=backend)

    assert percorso == str(out)
    assert out.read_bytes().startswith(b"\xff\xd8")
    assert backend.calls == [("https://stream", 12.5, str(out), {"Range": "x"})]


def test_extract_frame_backend_extractor_senza_file_e_un_errore(tmp_path):
    with pytest.raises(FrameExtractionError, match="non ha prodotto alcun file"):
        extract_frame("https://stream", 1.0, str(tmp_path / "missing.jpg"),
                      ffmpeg_backend=FakeExtractorBackend(produce=False))


# ----------------------------------------------------- MediaFlowController

def _esercizio():
    return {"nome": "Squat", "spiegazione": "", "note": "", "ripetizioni": "",
            "recupero": "", "gruppo": "", "video_url": "", "ts_start": None,
            "ts_finish": None, "frame_start": None, "frame_finish": None}


def make_media(esercizio=None, tmp_path=None, **iniettati):
    esercizio = esercizio or _esercizio()
    changed = []
    defaults = dict(
        log=[], on_change=lambda: changed.append(True),
        search=lambda nome: [{"id": "a", "title": f"{nome} tutorial", "duration": 100,
                              "webpage_url": "https://youtu.be/a"},
                             {"id": "b", "title": "unrelated", "duration": 50,
                              "webpage_url": "https://youtu.be/b"}],
        info_getter=lambda url: {"duration": 100, "title": "titolo da info"},
        extractor=lambda url, ts1, ts2, nome, out, ffmpeg_backend=None: (
            str(Path(out) / f"{nome}_start.jpg"), str(Path(out) / f"{nome}_finish.jpg")),
        auto_selector=lambda e, out, logger, ffmpeg_backend=None: e,
        cropper=lambda path, *pct: path,
        image_importer=_fake_image_importer,
        copier=lambda src, dst: Path(dst).write_bytes(Path(src).read_bytes()),
        stream_resolver=lambda url: (f"stream://{url}", {"User-Agent": "fake"}),
        single_extractor=lambda stream, ts, out, headers=None, ffmpeg_backend=None:
        Path(out).write_bytes(b"\xff\xd8jpeg"),
    )
    defaults.update(iniettati)
    controller = MediaFlowController(esercizio, str(tmp_path or "."), **defaults)
    return controller, esercizio, changed


def _fake_image_importer(src, nome, suffisso, out):
    if suffisso not in ("start", "finish"):
        raise ValueError(f"Suffisso frame non valido: '{suffisso}' (attesi 'start' o 'finish').")
    return str(Path(out) / f"{nome}_{suffisso}.jpg")


def test_cerca_filtra_e_espone_scelte_e_log_scarti(tmp_path):
    media, _, _ = make_media(tmp_path=tmp_path)

    scelte = media.cerca()

    assert [s.url for s in scelte] == ["https://youtu.be/a"]
    assert any("scartato 'unrelated'" in riga for riga in media.log)
    assert media.video_url == ""


def test_cerca_blocca_esercizi_senza_nome_e_errori_di_ricerca(tmp_path):
    vuoto = _esercizio()
    vuoto["nome"] = "  "
    media, _, _ = make_media(esercizio=vuoto, tmp_path=tmp_path)
    with pytest.raises(MediaFlowError, match="nome"):
        media.cerca()

    def rotto(nome):
        raise VideoSearchError("offline")
    media2, _, _ = make_media(tmp_path=tmp_path, search=rotto)
    with pytest.raises(MediaFlowError, match="Ricerca YouTube fallita"):
        media2.cerca()


def test_seleziona_e_url_manuale_propongono_ileuristiche_timestamp(tmp_path):
    media, esercizio, changed = make_media(tmp_path=tmp_path)

    media.cerca()
    media.seleziona(0)
    assert esercizio["video_url"] == "https://youtu.be/a"
    assert esercizio["ts_start"] == pytest.approx(10.0)
    assert esercizio["ts_finish"] == pytest.approx(50.0)

    media.url_manuale("  https://youtu.be/manual ")
    assert esercizio["video_url"] == "https://youtu.be/manual"
    assert changed


def test_timestamp_manuali_prevalgono_sulleuristica(tmp_path):
    media, esercizio, _ = make_media(tmp_path=tmp_path)
    media.url_manuale("https://youtu.be/manual")

    media.imposta_timestamp(ts_start=7.5, ts_finish=33.0)

    assert (esercizio["ts_start"], esercizio["ts_finish"]) == (7.5, 33.0)
    with pytest.raises(MediaFlowError, match="non valido"):
        media.imposta_timestamp(ts_start=-1)


def test_estrai_ripetuto_e_idempotente_se_i_frame_esistono(tmp_path):
    chiamata = []

    def ext(url, ts1, ts2, nome, out, ffmpeg_backend=None):
        chiamata.append(url)
        a, b = Path(out) / "a.jpg", Path(out) / "b.jpg"
        a.write_bytes(b"x")
        b.write_bytes(b"y")
        return str(a), str(b)

    media, esercizio, _ = make_media(tmp_path=tmp_path, extractor=ext)
    media.cerca()
    media.seleziona(0)

    assert media.estrai() is True
    assert media.estrai() is True
    assert len(chiamata) == 1  # secondo richiamo: frame gia su disco, nessuna ri-estrazione
    assert any("nessuna estrazione" in riga for riga in media.log)

    assert media.estrai(riestrai=True) is True
    assert len(chiamata) == 2  # la ri-estrazione forzata riparte


def test_estrai_blocca_timestamp_invertiti(tmp_path):
    media, _, _ = make_media(tmp_path=tmp_path)
    media.cerca()
    media.seleziona(0)
    media.imposta_timestamp(ts_start=40.0, ts_finish=10.0)

    with pytest.raises(MediaFlowError, match="FINISH deve essere maggiore"):
        media.estrai()


def test_propone_euristica_ricalcola_da_durata_notariprendendo_linfo(tmp_path):
    called = []

    def info(url):
        called.append(url)
        return {"duration": 200, "title": "t"}

    media, esercizio, _ = make_media(tmp_path=tmp_path, info_getter=info)
    media.url_manuale("https://youtu.be/x")
    media.imposta_timestamp(ts_start=99, ts_finish=199)

    media.proponi_euristica()

    assert esercizio["ts_start"] == pytest.approx(20.0)
    assert esercizio["ts_finish"] == pytest.approx(100.0)
    assert called == ["https://youtu.be/x"]


def test_estrai_con_video_selezionato_aggiorna_frame_e_log(tmp_path):
    media, esercizio, changed = make_media(tmp_path=tmp_path)
    media.cerca()
    media.seleziona(0)

    assert media.estrai() is True
    assert esercizio["frame_start"] == str(tmp_path / "Squat_start.jpg")
    assert esercizio["frame_finish"] == str(tmp_path / "Squat_finish.jpg")
    assert any("frame estratti" in riga for riga in media.log)
    assert changed


def test_estrai_senza_video_delega_scegli_ed_estrai(tmp_path):
    def auto(esercizio, out, logger, ffmpeg_backend=None):
        a, b = Path(out) / "a.jpg", Path(out) / "b.jpg"
        a.write_bytes(b"a")
        b.write_bytes(b"b")
        esercizio["frame_start"], esercizio["frame_finish"] = str(a), str(b)
        return esercizio

    media, esercizio, _ = make_media(tmp_path=tmp_path, auto_selector=auto)

    assert media.estrai() is True
    assert Path(esercizio["frame_start"]).read_bytes() == b"a"


def test_estrai_fallito_non_sporca_i_frame(tmp_path):
    def rotto(*a, **k):
        raise FrameExtractionError("403")

    media, esercizio, _ = make_media(tmp_path=tmp_path, extractor=rotto)
    media.cerca()
    media.seleziona(0)

    assert media.estrai() is False
    assert esercizio["frame_start"] is None
    assert any("estrazione fallita" in riga for riga in media.log)


def test_ritaglio_crea_backup_una_sola_volta_e_ripristino_riporta_indietro(tmp_path):
    frame = tmp_path / "squat_start.jpg"
    frame.write_bytes(b"originale")
    esercizio = _esercizio()
    esercizio["frame_start"] = str(frame)
    media, _, _ = make_media(esercizio=esercizio, tmp_path=tmp_path)

    assert media.puo_ripristinare("start") is False
    media.ritaglia("start", 10, 0, 10, 0)
    backup = Path(percorso_backup_frame(str(frame)))
    assert backup.read_bytes() == b"originale"
    assert media.puo_ripristinare("start") is True
    media.ripristina("start")
    assert frame.read_bytes() == b"originale"


def test_anteprima_crop_scrive_file_temporaneo_senza_mutare_il_frame(tmp_path):
    frame = tmp_path / "squat_start.jpg"
    frame.write_bytes(b"originale")
    prima = frame.read_bytes()
    esercizio = _esercizio()
    esercizio["frame_start"] = str(frame)
    media, _, _ = make_media(
        esercizio=esercizio, tmp_path=tmp_path,
        cropper=lambda path, s, a, d, b, output_path=None: Path(output_path).write_bytes(b"crop") and output_path,
    )

    anteprima = media.anteprima_crop("start", 10, 10, 10, 10)

    assert anteprima == str(tmp_path / "_crop_preview_start.jpg")
    assert Path(anteprima).read_bytes() == b"crop"
    assert frame.read_bytes() == prima


def test_ritaglio_senza_frame_o_suffisso_invalido_sollevano_errore(tmp_path):
    media, _, _ = make_media(tmp_path=tmp_path)
    with pytest.raises(MediaFlowError, match="Frame non ancora estratto"):
        media.ritaglia("start", 5, 5, 5, 5)
    with pytest.raises(MediaFlowError, match="Suffisso frame non valido"):
        media.ripristina("lato")


def test_media_transazione_undo_redo_ripristina_manifest_e_byte_del_crop(tmp_path):
    frame = tmp_path / "squat_start.jpg"
    frame.write_bytes(b"originale")
    esercizio = _esercizio()
    esercizio["frame_start"] = str(frame)
    editor = SchedaEditorController([esercizio], percorso_bundle="s.scheda")
    media, _, _ = make_media(
        esercizio=esercizio, tmp_path=tmp_path,
        cropper=lambda path, *args, **kwargs: Path(path).write_bytes(b"ritagliato"),
    )
    media._transaction = lambda operation: editor.transazione_media(
        operation, output_dir=tmp_path)

    media.ritaglia("start", 10, 0, 10, 0)
    assert frame.read_bytes() == b"ritagliato"
    assert Path(percorso_backup_frame(str(frame))).read_bytes() == b"originale"
    assert editor.undo() is True
    assert frame.read_bytes() == b"originale"
    assert not Path(percorso_backup_frame(str(frame))).exists()
    assert editor.redo() is True
    assert frame.read_bytes() == b"ritagliato"
    assert Path(percorso_backup_frame(str(frame))).read_bytes() == b"originale"


def test_media_transazione_fallita_rimuove_output_parziale(tmp_path):
    esercizio = _esercizio()

    def extractor(url, ts_start, ts_finish, nome, output_dir, ffmpeg_backend=None):
        (Path(output_dir) / "parziale.jpg").write_bytes(b"parziale")
        raise FrameExtractionError("errore a meta")

    editor = SchedaEditorController([esercizio], percorso_bundle="s.scheda")
    media, _, _ = make_media(esercizio=esercizio, tmp_path=tmp_path, extractor=extractor)
    media.url_manuale("https://youtu.be/a")
    media._transaction = lambda operation: editor.transazione_media(
        operation, output_dir=tmp_path)

    assert media.estrai() is False
    assert esercizio["frame_start"] is None
    assert not (tmp_path / "parziale.jpg").exists()


def test_editor_e_media_condividono_la_stessa_cronologia(tmp_path):
    frame = tmp_path / "squat_start.jpg"
    frame.write_bytes(b"iniziale")
    esercizio = _esercizio()
    esercizio["frame_start"] = str(frame)
    editor = SchedaEditorController([esercizio], percorso_bundle="s.scheda")
    media = MediaFlowController(
        esercizio, str(tmp_path),
        cropper=lambda path, *args, **kwargs: Path(path).write_bytes(b"media"),
        copier=lambda src, dst: Path(dst).write_bytes(Path(src).read_bytes()),
        transaction=lambda operation: editor.transazione_media(
            operation, output_dir=tmp_path),
    )

    editor.aggiorna(0, note="testo")
    media.ritaglia("start", 5, 5, 5, 5)
    assert editor.cronologia_dimensione == 2
    assert frame.read_bytes() == b"media"

    editor.undo()
    assert frame.read_bytes() == b"iniziale"
    assert editor.esercizi[0]["note"] == "testo"
    editor.undo()
    assert editor.esercizi[0]["note"] == ""


def test_importa_immagine_aggiorna_il_frame_giusto(tmp_path):
    media, esercizio, changed = make_media(tmp_path=tmp_path)

    percorso = media.importa_immagine(str(tmp_path / "foto.png"), "finish")

    assert esercizio["frame_finish"] == percorso == str(tmp_path / "Squat_finish.jpg")
    assert changed

    with pytest.raises(MediaFlowError, match="Suffisso frame non valido"):
        media.importa_immagine(str(tmp_path / "foto.png"), "errato")


# ------------------------------------------------- AndroidFrameExtractor MMR

class FakeJava:
    def __init__(self, bitmap):
        self.bitmap = bitmap
        self.calls = []
        self.compressions = []

    def autoclass(self, nome):
        outer = self

        class Retriever:
            def setDataSource(self, url, headers=None):
                outer.calls.append(("source", url, headers))

            def getFrameAtTime(self, us, option):
                outer.calls.append(("frame", us, option))
                return outer.bitmap

            def release(self):
                outer.calls.append(("release",))

        class Format:
            JPEG = "jpeg"

        class FileStream:
            def __init__(self, path):
                self.path = path

            def flush(self):
                outer.calls.append(("flush",))

            def close(self):
                outer.calls.append(("close",))

        class HashMap(dict):
            def put(self, key, value):
                self[key] = value

        return {"android.media.MediaMetadataRetriever": Retriever,
                "android.graphics.Bitmap$CompressFormat": Format,
                "java.io.FileOutputStream": FileStream,
                "java.util.HashMap": HashMap}[nome]


class FakeBitmap:
    def compress(self, fmt, quality, stream):
        self.last = (fmt, quality, stream.path)
        Path(stream.path).write_bytes(b"\xff\xd8jpeg")
        return True


def test_android_frame_extractor_ortodosso_scrive_il_jpeg(tmp_path):
    java = FakeJava(bitmap=FakeBitmap())
    extractor = AndroidFrameExtractor(autoclass_factory=java.autoclass)
    out = tmp_path / "frame.jpg"

    risultato = extractor.extract("https://stream", 12.34, str(out), {"Referer": "x"})

    assert risultato == str(out)
    assert out.read_bytes() == b"\xff\xd8jpeg"
    assert ("source", "https://stream", {"Referer": "x"}) in java.calls
    assert ("frame", 12_340_000, 2) in java.calls
    assert ("release",) in java.calls and ("close",) in java.calls


def test_android_frame_extractor_senza_frame_diventa_errore(tmp_path):
    java = FakeJava(bitmap=None)
    extractor = AndroidFrameExtractor(autoclass_factory=java.autoclass)

    with pytest.raises(FrameExtractionError, match="nessun frame"):
        extractor.extract("https://stream", 5, str(tmp_path / "x.jpg"))


# ---------------------------------------------------------------- scrub slider

def test_url_con_inizio_posisziona_il_playback():
    assert url_con_inizio("https://youtu.be/abc", 50) == "https://youtu.be/abc#t=50s"
    assert url_con_inizio("https://www.youtube.com/watch?v=abc", 12) == \
        "https://www.youtube.com/watch?v=abc&t=12s"
    assert url_con_inizio("https://www.youtube.com/watch?v=abc&t=3s&x=1", 40) == \
        "https://www.youtube.com/watch?v=abc&t=40s&x=1"
    assert url_con_inizio("https://www.youtube.com/watch?v=abc#frag", 5) == \
        "https://www.youtube.com/watch?v=abc&t=5s"
    assert url_con_inizio("", 5) == ""


def test_url_per_play_usa_il_timestamp_inizio():
    e = _esercizio()
    e["video_url"] = "https://youtu.be/abc"
    e["ts_start"] = 33.6
    media, _, _ = make_media(esercizio=e)

    assert media.url_per_play() == "https://youtu.be/abc#t=34s"
    assert media.url_per_play(10) == "https://youtu.be/abc#t=10s"


def test_url_per_play_senza_video_e_un_errore():
    media, _, _ = make_media()
    with pytest.raises(MediaFlowError, match="Seleziona prima un video"):
        media.url_per_play()


def test_assicura_durata_completa_i_video_del_manifest(tmp_path):
    e = _esercizio()
    e["video_url"] = "https://youtu.be/xyz"
    chiamate = []

    def info(url):
        chiamate.append(url)
        return {"duration": 100.0, "title": "t"}

    media, _, _ = make_media(esercizio=e, tmp_path=tmp_path, info_getter=info)

    assert media.durata is None
    assert media.assicura_durata() == 100.0
    assert media.assicura_durata() == 100.0
    assert chiamate == ["https://youtu.be/xyz"]


def test_anteprima_scrub_risolve_lo_stream_una_sola_volta(tmp_path):
    risoluzioni = []

    def resolver(url):
        risoluzioni.append(url)
        return f"stream://{url}", {"User-Agent": "fake"}

    estrazioni = []

    def single(stream, ts, out, headers=None, ffmpeg_backend=None):
        estrazioni.append((stream, ts, out))
        Path(out).write_bytes(b"\xff\xd8jpeg")

    media, esercizio, _ = make_media(tmp_path=tmp_path, stream_resolver=resolver,
                                     single_extractor=single)
    media.url_manuale("https://youtu.be/a")

    percorso = media.anteprima_scrub("start", 33.0)
    percorso2 = media.anteprima_scrub("finish", 44.0)

    assert percorso.endswith("_scrub_preview_start.jpg")
    assert percorso2.endswith("_scrub_preview_finish.jpg")
    assert Path(percorso).exists()
    assert risoluzioni == ["https://youtu.be/a"]
    assert [ts for _, ts, _ in estrazioni] == [33.0, 44.0]
    assert esercizio["frame_start"] is None and esercizio["frame_finish"] is None


def test_anteprima_scrub_clampa_sulla_durata_e_esige_un_video(tmp_path):
    estratti = []
    media, _, _ = make_media(tmp_path=tmp_path,
                             single_extractor=lambda stream, ts, out, headers=None,
                             ffmpeg_backend=None: estratti.append(ts) or Path(out).write_bytes(b"x"))
    with pytest.raises(MediaFlowError, match="Seleziona prima un video"):
        media.anteprima_scrub("start", 10)
    media.url_manuale("https://youtu.be/a")  # info_getter dice durata 100
    media.anteprima_scrub("start", 150)
    assert estratti == [pytest.approx(99.9)]


def test_anteprima_scrub_ri_risolve_lo_stream_scaduto(tmp_path):
    tentativi = {"n": 0}

    def single(stream, ts, out, headers=None, ffmpeg_backend=None):
        tentativi["n"] += 1
        if tentativi["n"] == 1:
            raise FrameExtractionError("403")
        Path(out).write_bytes(b"\xff\xd8jpeg")

    media, _, _ = make_media(tmp_path=tmp_path, single_extractor=single)
    media.url_manuale("https://youtu.be/a")

    percorso = media.anteprima_scrub("start", 5)

    assert Path(percorso).exists() and tentativi["n"] == 2


def test_anteprima_scrub_doppio_fallimento_diventa_mediaflow_error(tmp_path):
    def single(stream, ts, out, headers=None, ffmpeg_backend=None):
        raise FrameExtractionError("boom")

    media, _, _ = make_media(tmp_path=tmp_path, single_extractor=single)
    media.url_manuale("https://youtu.be/a")

    with pytest.raises(MediaFlowError, match="Anteprima scrub fallita"):
        media.anteprima_scrub("start", 5)
