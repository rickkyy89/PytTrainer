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
from kivy.uix.button import Button
from kivy.uix.popup import Popup

from kivy_app.material import (BUTTON_HEIGHTS, ViewportMetrics, adaptive_profile,
                               imposta_pulsanti, pulsanti_correnti)
from kivy_app.media import MediaFlowError
from kivy_app.media_screen import MediaScreen


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

    def pronto(self):
        return False

    def frame(self, suffisso):
        return None

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

    sliders = screen._crop_sliders["start"]
    screen._apply_crop("start", sliders)
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
def test_reflow_committa_il_timestamp_focused_e_preserva_tutti_i_crop(monkeypatch):
    media = MediaStub()
    screen = make_screen(media)
    screen.ts_start.text = "12,5"
    screen.ts_start.focus = True
    expected = {
        "start": {"sinistra": 3, "alto": 7, "destra": 11, "basso": 13},
        "finish": {"sinistra": 5, "alto": 9, "destra": 15, "basso": 17},
    }
    screen._reflowing = True  # avoid crop-preview jobs while arranging the fixture
    for suffix, values in expected.items():
        for side, value in values.items():
            screen._crop_sliders[suffix][side].value = value
    screen._reflowing = False

    compact = adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"))
    monkeypatch.setattr("kivy_app.media_screen.profile_for_window", lambda window: compact)
    screen._layout_key = object()  # force the rebuild path
    screen._riflow()
    Clock.tick()

    assert media.ts_start == pytest.approx(12.5)
    assert screen.ts_start.text == "12.5"
    for suffix, values in expected.items():
        assert {side: slider.value for side, slider in
                screen._crop_sliders[suffix].items()} == values


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
