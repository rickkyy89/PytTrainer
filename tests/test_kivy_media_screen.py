"""Behavioral tests for MediaScreen review findings.

These tests stay at the media seam: no main/common/editor/export/workout code
is patched or imported. Workers are inert stubs so busy/concurrency behavior
is deterministic.
"""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

kivy = pytest.importorskip("kivy")

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from PIL import Image as PillowImage

from kivy_app.crop_layout import Rect
from kivy_app.material import (BUTTON_HEIGHTS, ViewportMetrics, adaptive_profile,
                               imposta_pulsanti, pulsanti_correnti)
from kivy_app.media import MediaFlowError
from kivy_app.media_screen import MediaScreen, _TelaRitaglio


requires_window = pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")


class ThreadStub:
    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        pass


class MediaStub:
    def __init__(self):
        self.video_url = "https://youtu.be/x"
        self.durata = 100.0
        self.ts_start = 10.0
        self.ts_finish = 50.0
        self.titolo_video = "Squat"
        self.scelte = []
        self.calls = []
        self.frames = {}

    def pronto(self):
        return False

    def frame(self, suffisso):
        return self.frames.get(suffisso)

    def imposta_timestamp(self, **updates):
        self.calls.append(("timestamp", updates))
        for key, value in updates.items():
            setattr(self, key, value)

    def proponi_euristica(self):
        self.calls.append(("euristica",))

    def ritaglia(self, suffisso, *values):
        self.calls.append(("ritaglia", suffisso, values))

    def ripristina(self, suffisso):
        self.calls.append(("ripristina", suffisso))

    def importa_immagine(self, path, suffisso):
        self.calls.append(("immagine", path, suffisso))

    def crea_placeholder(self, suffisso):
        self.calls.append(("placeholder", suffisso))

    def percorso_anteprima(self, suffisso):
        return str(PROJECT_ROOT / f"_{suffisso}.jpg")

    def url_per_play(self):
        return self.video_url


@pytest.fixture(autouse=True)
def restore_button_preset():
    before = pulsanti_correnti()
    yield
    imposta_pulsanti(before)


def make_screen(media=None, on_menu=None):
    return MediaScreen(media or MediaStub(), on_back=lambda: None, on_menu=on_menu)


@requires_window
def test_busy_disabilita_tutti_i_controlli_mutanti_e_i_guard_bloccano_stale_callbacks(
        monkeypatch):
    monkeypatch.setattr("kivy_app.media_screen.threading.Thread", ThreadStub)
    notices = []
    monkeypatch.setattr("kivy_app.media_screen.mostra_snackbar",
                        lambda parent, text: notices.append(text))
    picked = []
    monkeypatch.setattr("kivy_app.media_screen.choose_file",
                        lambda *args, **kwargs: picked.append(True))
    media = MediaStub()
    exits = []
    screen = MediaScreen(media, on_back=lambda: exits.append(True))

    screen._run_async(lambda: None)

    assert screen.busy is True
    assert screen._back.disabled and screen._menu.disabled
    assert screen._mutating_controls
    assert all(control.disabled for control in screen._mutating_controls)
    media.calls.clear()  # ignore timestamp commit performed before entering busy

    screen._apri_ritaglio("start")
    screen._restore("start")
    screen._import_image("start")
    screen._placeholder("start")
    screen._apri_disegno("start")
    screen._apply_heuristic()
    assert screen._manual_url_popup() is None
    screen._exit()

    assert media.calls == []
    assert picked == []
    assert exits == []
    assert notices and all("Attendere" in text for text in notices)

    screen._finish_async(None)
    assert screen.busy is False
    assert not screen._back.disabled and not screen._menu.disabled
    assert all(not control.disabled for control in screen._mutating_controls)


@requires_window
def test_reflow_committa_il_timestamp_focused_senza_stato_slider_crop(monkeypatch):
    media = MediaStub()
    screen = make_screen(media)
    screen.ts_start.text = "12,5"
    screen.ts_start.focus = True
    compact = adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"))
    monkeypatch.setattr("kivy_app.media_screen.profile_for_window", lambda window: compact)
    screen._layout_key = object()  # force the rebuild path
    screen._riflow()
    Clock.tick()

    assert media.ts_start == pytest.approx(12.5)
    assert screen.ts_start.text == "12.5"
    assert not hasattr(screen, "_crop_sliders")
    assert "crop" not in screen._capture_reflow_state()


@requires_window
def test_reflow_non_perde_testo_timestamp_non_valido(monkeypatch):
    media = MediaStub()
    screen = make_screen(media)
    errors = []
    screen._mostra_errore = lambda error: errors.append(str(error))
    screen.ts_finish.text = "non-numero"
    screen.ts_finish.focus = True

    compact = adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"))
    monkeypatch.setattr("kivy_app.media_screen.profile_for_window", lambda window: compact)
    screen._layout_key = object()
    screen._riflow()

    assert screen.ts_finish.text == "non-numero"
    assert errors == ["Timestamp non numerico: non-numero"]
    assert media.ts_finish == 50.0


@pytest.mark.parametrize("preset", ("compact", "standard", "large"))
@requires_window
def test_app_bar_azioni_dirette_e_menu_rispettano_esattamente_44_52_60(preset):
    imposta_pulsanti(preset)
    expected = dp(BUTTON_HEIGHTS[preset])
    screen = make_screen()

    header = screen.children[-1]
    assert header.height == pytest.approx(expected)
    assert screen._back.width == pytest.approx(expected)
    assert screen._menu.width == pytest.approx(expected)
    play = next(w for w in screen.walk(restrict=True)
                if isinstance(w, Button) and w.text == "Play")
    assert play.parent.height == pytest.approx(expected)

    menu = screen._open_panel_menu("start", screen._menu)
    buttons = [w for w in menu.overlay.walk(restrict=True) if isinstance(w, Button)]
    assert buttons
    assert all(button.height == pytest.approx(expected) for button in buttons)
    menu.dismiss()


@requires_window
def test_successi_usano_snackbar_errori_popup_e_impostazioni_e_diretta(monkeypatch):
    notices = []
    monkeypatch.setattr("kivy_app.media_screen.mostra_snackbar",
                        lambda parent, text: notices.append(text))
    media = MediaStub()

    class Owner:
        def __init__(self):
            self.settings = 0
            self.menu = 0

        def show_settings(self):
            self.settings += 1

        def apri_menu(self, anchor=None):
            self.menu += 1

    owner = Owner()
    screen = make_screen(media, owner.apri_menu)
    screen._placeholder("start")
    assert notices == ["Placeholder START impostato."]

    media.ripristina = lambda suffix: (_ for _ in ()).throw(MediaFlowError("backup assente"))
    screen._restore("start")
    assert screen._error_popup is not None
    assert screen._error_popup.title == "Errore"
    screen._error_popup.dismiss(animation=False)

    captured = []
    monkeypatch.setattr("kivy_app.media_screen.apri_menu",
                        lambda actions, anchor=None: captured.extend(actions))
    screen._open_media_menu(screen._menu)
    labels = [label for label, _ in captured]
    assert labels == ["URL manuale…", "Euristica 10%/50%", "Impostazioni"]
    dict(captured)["Impostazioni"]()
    assert owner.settings == 1
    assert owner.menu == 0


@requires_window
def test_placeholder_del_pannello_start_non_piazza_quello_finish():
    """Regression: late-bound panel actions made every START button act on FINISH."""
    media = MediaStub()
    screen = make_screen(media)
    try:
        panels = {s: screen.frames_row.children[-1 if s == "start" else 0]
                  for s in ("start", "finish")}  # children e' in ordine inverso di add
        for suffisso, panel in panels.items():
            riga = next(w for w in panel.walk(restrict=True)
                        if isinstance(w, BoxLayout)
                        and any(isinstance(c, Button) and c.text == "Placeholder"
                                for c in w.children))
            pulsante = next(c for c in riga.children if getattr(c, "text", "") == "Placeholder")
            pulsante.dispatch("on_release")
            assert media.calls[-1] == ("placeholder", suffisso)
    finally:
        if hasattr(screen, "dispose"):
            screen.dispose()


@requires_window
def test_pannelli_hanno_solo_placeholder_e_kebab_con_quattro_azioni(monkeypatch):
    screen = make_screen()
    assert not hasattr(screen, "_crop_sliders")
    for panel in screen.frames_row.children:
        riga = panel.children[0]
        pulsanti = [child for child in riga.children if isinstance(child, Button)]
        assert len(pulsanti) == 2
        assert sum(button.text == "Placeholder" for button in pulsanti) == 1

    captured = []
    monkeypatch.setattr("kivy_app.media_screen.apri_menu",
                        lambda actions, anchor=None: captured.extend(actions))
    screen._open_panel_menu("start", screen._menu)
    assert [label for label, _ in captured] == [
        "Ritaglia", "Disegna", "Immagine…", "Ripristina",
    ]


def _frame_jpeg(tmp_path, nome="frame.jpg"):
    percorso = tmp_path / nome
    PillowImage.new("RGB", (200, 100), "white").save(percorso, "JPEG")
    return str(percorso)


def _pulsante(popup, testo):
    return next(widget for widget in popup.content.walk(restrict=True)
                if isinstance(widget, Button) and widget.text == testo)


def _tela(popup):
    return next(widget for widget in popup.content.walk(restrict=True)
                if isinstance(widget, _TelaRitaglio))


class _TouchSimulato:
    """Touch minimo con coordinate finestra e semantica grab di Kivy."""

    button = "left"

    def __init__(self, pos):
        self.pos = pos
        self.grab_current = None

    @property
    def x(self):
        return self.pos[0]

    @property
    def y(self):
        return self.pos[1]

    def grab(self, widget):
        self.grab_current = widget

    def ungrab(self, widget):
        if self.grab_current is widget:
            self.grab_current = None


@requires_window
def test_tela_ritaglio_immagine_e_selezione_condividono_coordinate(tmp_path):
    tela = _TelaRitaglio(_frame_jpeg(tmp_path), (200, 100),
                         pos=(37, 53), size=(400, 300), size_hint=(None, None))
    tela._aggiorna_geometria()

    image = tela._image_rect
    assert tela.immagine.pos == pytest.approx((image.left, image.bottom))
    assert tela.immagine.size == pytest.approx((image.width, image.height))
    assert tela._selection == image  # la selezione iniziale copre tutto il frame


@requires_window
def test_touch_finestra_restringe_angolo_e_trascina_corpo_dal_centro(tmp_path):
    tela = _TelaRitaglio(_frame_jpeg(tmp_path), (200, 100),
                         pos=(37, 53), size=(400, 300), size_hint=(None, None))
    tela._aggiorna_geometria()
    image = tela._image_rect

    # Il top-left entra verso il centro; bottom-right deve restare fisso.
    angolo = _TouchSimulato(tela.to_parent(image.left, image.top))
    assert tela.on_touch_down(angolo)
    angolo.pos = tela.to_parent(image.left + 60, image.top - 40)
    assert tela.on_touch_move(angolo)
    ristretta = tela._selection
    assert ristretta.left > image.left and ristretta.top < image.top
    assert ristretta.right == pytest.approx(image.right)
    assert ristretta.bottom == pytest.approx(image.bottom)
    assert tela.on_touch_up(angolo)

    # Il centro immagine e' nel corpo: la selezione si sposta, senza deformarsi.
    centro = ((image.left + image.right) / 2, (image.bottom + image.top) / 2)
    corpo = _TouchSimulato(tela.to_parent(*centro))
    assert tela.on_touch_down(corpo)
    assert tela._drag_target == "body"
    corpo.pos = tela.to_parent(centro[0] - 20, centro[1] + 15)
    assert tela.on_touch_move(corpo)
    spostata = tela._selection
    assert spostata.width == pytest.approx(ristretta.width)
    assert spostata.height == pytest.approx(ristretta.height)
    assert spostata.left < ristretta.left and spostata.bottom > ristretta.bottom
    assert tela.on_touch_up(corpo)


@pytest.mark.parametrize("suffisso", ("start", "finish"))
@requires_window
def test_popup_ritaglio_ha_titolo_corretto_per_frame_valido(tmp_path, suffisso):
    media = MediaStub()
    media.frames[suffisso] = _frame_jpeg(tmp_path, f"{suffisso}.jpg")
    popup = make_screen(media)._apri_ritaglio(suffisso)
    try:
        assert popup.title == f"Ritaglia frame {suffisso.upper()}"
    finally:
        popup.dismiss(animation=False)


@requires_window
def test_selezione_nota_applica_percentuali_aggiorna_preview_e_informa(
        tmp_path, monkeypatch):
    notices = []
    monkeypatch.setattr("kivy_app.media_screen.mostra_snackbar",
                        lambda parent, text: notices.append(text))
    media = MediaStub()
    media.frames["start"] = _frame_jpeg(tmp_path)
    screen = make_screen(media)
    reloads = []
    screen.preview_start.reload = lambda: reloads.append(True)
    popup = screen._apri_ritaglio("start")
    tela = _tela(popup)
    tela._image_rect = Rect(0, 0, 200, 100)
    tela._selection = Rect(20, 15, 140, 80)

    _pulsante(popup, "Applica").dispatch("on_release")

    assert media.calls[-1][0:2] == ("ritaglia", "start")
    assert media.calls[-1][2] == pytest.approx((10, 20, 30, 15))
    assert reloads == [True]
    assert notices == ["Ritaglio applicato."]


@requires_window
def test_annulla_e_ritaglio_nullo_non_mutano(tmp_path):
    media = MediaStub()
    media.frames["start"] = _frame_jpeg(tmp_path)
    screen = make_screen(media)
    popup = screen._apri_ritaglio("start")
    _pulsante(popup, "Annulla").dispatch("on_release")
    assert not any(call[0] == "ritaglia" for call in media.calls)

    popup = screen._apri_ritaglio("start")
    tela = _tela(popup)
    tela._selection = tela._image_rect
    _pulsante(popup, "Applica").dispatch("on_release")
    assert not any(call[0] == "ritaglia" for call in media.calls)


@requires_window
def test_frame_mancante_mostra_errore_senza_popup():
    screen = make_screen()
    errors = []
    screen._mostra_errore = lambda error: errors.append(str(error))
    assert screen._apri_ritaglio("start") is None
    assert errors == ["Frame non ancora estratto: niente da ritagliare."]


@requires_window
def test_busy_blocca_apertura_callback_stale_e_controllo_viene_rimosso(
        tmp_path, monkeypatch):
    notices = []
    monkeypatch.setattr("kivy_app.media_screen.mostra_snackbar",
                        lambda parent, text: notices.append(text))
    media = MediaStub()
    media.frames["start"] = _frame_jpeg(tmp_path)
    screen = make_screen(media)
    popup = screen._apri_ritaglio("start")
    applica = _pulsante(popup, "Applica")
    assert applica in screen._mutating_controls

    screen._busy = True
    assert screen._apri_ritaglio("start") is None
    applica.dispatch("on_release")
    assert not any(call[0] == "ritaglia" for call in media.calls)
    assert notices and all("Attendere" in text for text in notices)
    screen._busy = False
    popup.dismiss(animation=False)
    assert applica not in screen._mutating_controls


@requires_window
def test_campi_timestamp_affiancati_orizzontalmente():
    """Start e Finish condividono la stessa riga (due colonne)."""
    screen = make_screen(MediaStub())
    try:
        cella_start = screen.ts_start.parent
        cella_finish = screen.ts_finish.parent
        assert cella_start is not cella_finish
        contenitore = cella_start.parent
        assert isinstance(contenitore, BoxLayout)
        assert contenitore.orientation == "horizontal"
        assert cella_finish.parent is contenitore
    finally:
        if hasattr(screen, "dispose"):
            screen.dispose()
