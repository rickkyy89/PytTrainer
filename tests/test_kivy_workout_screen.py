"""Redesign behavior of the workout Kivy screen (app bar and kebab).

Kivy layer of the confirmed Workout redesign: uniform back+title+kebab app
bar, "Azzera" moved into the contextual kebab while "Stop" stays a direct
timer-bar control and the per-exercise recovery/video buttons stay on the
cards.
"""

import sys
from pathlib import Path

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
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from kivy_app.material import imposta_pulsanti, pulsanti_correnti
from kivy_app.workout import WorkoutSessionController
from kivy_app.workout_screen import WorkoutScreen

requires_window = pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")


@pytest.fixture(scope="module", autouse=True)
def app_kivymd():
    """MDCard richiede un'istanza MDApp; basta costruirla, senza run()."""
    from kivy.app import App
    if App.get_running_app() is not None:
        return App.get_running_app()
    from kivymd.app import MDApp
    app = MDApp()
    return app


ESERCIZI = [
    {"nome": "Squat", "spiegazione": "Scendi controllando.", "note": "Ginocchia in linea.",
     "ripetizioni": "3x12", "recupero": "90 SEC", "gruppo": "Gambe",
     "video_url": "https://youtu.test/squat", "ts_start": None, "ts_finish": None,
     "frame_start": "", "frame_finish": ""},
    {"nome": "Plank", "spiegazione": "", "note": "",
     "ripetizioni": "1x60s", "recupero": "1:30", "gruppo": "",
     "video_url": "", "ts_start": None, "ts_finish": None,
     "frame_start": "", "frame_finish": ""},
]


def nuova_vista(on_menu="default"):
    sessione = WorkoutSessionController([dict(e) for e in ESERCIZI])
    cb = (lambda anchor=None: None) if on_menu == "default" else on_menu
    screen = WorkoutScreen(sessione, on_back=lambda: None,
                           notifier=lambda: None, on_menu=cb)
    screen._menu.pos = (max(Window.width - 60, 0), max(Window.height - 60, 0))
    return screen, sessione


def voci_menu(menu):
    return [w.text for w in menu.overlay.walk(restrict=True) if isinstance(w, Button)]


def premi_voce(contenitore, testo):
    contenitore = getattr(contenitore, "overlay", contenitore)  # MenuAperto o widget
    for widget in contenitore.walk(restrict=True):
        if isinstance(widget, Button) and widget.text == testo:
            widget.dispatch("on_release")
            return True
    return False


@requires_window
def test_l_app_bar_e_back_titolo_kebab_senza_azzera_direct():
    screen, _ = nuova_vista()
    try:
        header = screen.children[-1]
        etichette = [w.text for w in header.children]
        from kivy_app.icons import glifo
        assert glifo("chevron-left", "‹")[0] in etichette
        assert glifo("dots-vertical", "⋮")[0] in etichette
        assert any("Allenamento" in t for t in etichette if isinstance(t, str))
        pulsanti = [w.text for w in screen.walk() if isinstance(w, Button)]
        assert "Azzera" not in pulsanti  # vive solo nel kebab, non piu' nell'header
    finally:
        screen.dispose()


@requires_window
def test_stop_timer_rimane_un_controllo_direct_sulla_bar():
    screen, sessione = nuova_vista()
    try:
        assert screen._start_timer(0) is None
        assert sessione.recupero_attivo() is True
        assert screen.timer_label.text == "Recupero 1:30"
        assert premi_voce(screen, "Stop")  # presente nella vista, non solo nel kebab
        assert sessione.recupero_attivo() is False
        assert screen.timer_label.text == "Recupero: —"
    finally:
        screen.dispose()


@requires_window
def test_kebab_workout_azzera_piu_menu_globale_in_ordine():
    screen, _ = nuova_vista()
    try:
        menu = screen._open_workout_menu(screen._menu)
        assert voci_menu(menu) == ["Azzera", "Impostazioni"]
        menu.dismiss()
    finally:
        screen.dispose()


@requires_window
def test_senza_on_menu_il_kebab_workout_ha_solo_azzera():
    screen, _ = nuova_vista(on_menu=None)
    try:
        menu = screen._open_workout_menu(screen._menu)
        assert voci_menu(menu) == ["Azzera"]
        menu.dismiss()
    finally:
        screen.dispose()


@requires_window
def test_azzera_dal_kebab_pulisce_spunte_progresso_e_timer(monkeypatch):
    feedback = []
    monkeypatch.setattr("kivy_app.workout_screen.mostra_snackbar",
                        lambda parent, text, durata=3.0: feedback.append((parent, text)))
    screen, sessione = nuova_vista()
    try:
        screen._start_timer(0)
        assert screen.timer_label.text == "Recupero 1:30"
        screen._toggle(0, True)
        assert sessione.conteggio_completati() == 1
        menu = screen._open_workout_menu(screen._menu)
        assert premi_voce(menu, "Azzera")
        assert sessione.conteggio_completati() == 0
        from kivy_app.icons import glifo
        assert screen._checkboxes[0].text == glifo("checkbox-blank-outline", "[ ]")[0]
        assert "0/2" in screen.progress_label.text
        assert screen.timer_label.text == "Recupero: —"
        assert sessione.recupero_attivo() is False
        assert feedback == [(screen, "Allenamento azzerato.")]
    finally:
        screen.dispose()


@requires_window
def test_controlli_per_esercizio_restano_sulle_card():
    screen, _ = nuova_vista()
    try:
        pulsanti = [w.text for w in screen.walk() if isinstance(w, Button)]
        assert "» Recupero 1" in pulsanti and "» Recupero 2" in pulsanti
        assert "» Video" in pulsanti  # solo lo Squat ha la video_url
    finally:
        screen.dispose()


@requires_window
def test_menu_genitore_riceve_l_anchor_quando_lo_accetta():
    visti = []
    screen, _ = nuova_vista(on_menu=lambda anchor=None: visti.append(anchor))
    try:
        screen._invoke_parent_menu(screen._menu)
        assert visti == [screen._menu]
    finally:
        screen.dispose()

    legacy = []
    screen_legacy, _ = nuova_vista(on_menu=lambda: legacy.append("zero-arg"))
    try:
        screen_legacy._invoke_parent_menu(screen_legacy._menu)
        assert legacy == ["zero-arg"]
    finally:
        screen_legacy.dispose()


@requires_window
def test_impostazioni_invoca_il_parent_in_una_sola_selezione():
    visti = []
    screen, _ = nuova_vista(on_menu=lambda anchor=None: visti.append(anchor))
    try:
        menu = screen._open_workout_menu(screen._menu)
        assert premi_voce(menu, "Impostazioni")
        assert visti == [screen._menu]
    finally:
        screen.dispose()


@requires_window
@pytest.mark.parametrize("preset,atteso", [("compact", 44), ("standard", 52), ("large", 60)])
def test_workout_rispetta_i_tre_preset_su_barre_e_card(preset, atteso):
    precedente = pulsanti_correnti()
    screen = None
    try:
        imposta_pulsanti(preset)
        screen, _ = nuova_vista()
        assert screen.header.height == pytest.approx(dp(atteso))
        assert screen._back.width == pytest.approx(dp(atteso))
        assert screen._menu.width == pytest.approx(dp(atteso))
        assert screen.timer_bar.height == pytest.approx(dp(atteso))
        recupero = next(w for w in screen.walk()
                        if isinstance(w, Button) and w.text == "» Recupero 1")
        assert recupero.parent.height == pytest.approx(dp(atteso))
    finally:
        if screen is not None:
            screen.dispose()
        imposta_pulsanti(precedente)


@requires_window
def test_casella_e_titolo_condividono_la_riga_senza_sovrapporsi():
    """Regressione: la texture del titolo non deve finire sotto la casella.

    Kivy disegna la texture centrata sul widget, quindi un ``text_size`` piu'
    largo del label fa scivolare il testo a sinistra: sul tablet (density 2) il
    margine in pixel grezzi non copriva piu' la cella della checkbox.
    """
    host = BoxLayout()
    screen, _ = nuova_vista()
    host.add_widget(screen)
    try:
        host.size = (800, 1280)
        for _ in range(10):  # nested layouts settle on the following frames
            Clock.tick()
        for card in screen.cards.children:
            riga = next(w for w in card.children
                        if isinstance(w, BoxLayout)
                        and any(isinstance(c, FloatLayout) for c in w.children))
            cella = next(w for w in riga.children if isinstance(w, FloatLayout))
            casella = next(w for w in cella.children if isinstance(w, Button))
            titolo = next(w for w in riga.children if isinstance(w, Label))
            assert titolo.text_size[0] <= titolo.width
            assert titolo.x >= casella.right
            assert titolo.center_y == pytest.approx(casella.center_y)
    finally:
        host.remove_widget(screen)
        screen.dispose()


@requires_window
def test_workout_riapplica_il_preset_al_ritorno_da_impostazioni():
    precedente = pulsanti_correnti()
    host = BoxLayout()
    screen = None
    try:
        imposta_pulsanti("compact")
        screen, sessione = nuova_vista()
        host.add_widget(screen)
        screen._start_timer(0)
        screen._toggle(0, True)
        host.remove_widget(screen)
        imposta_pulsanti("large")
        host.add_widget(screen)
        assert screen.header.height == pytest.approx(dp(60))
        assert screen.timer_bar.height == pytest.approx(dp(60))
        assert sessione.recupero_attivo() is True
        assert sessione.conteggio_completati() == 1
    finally:
        if screen is not None:
            screen.dispose()
        imposta_pulsanti(precedente)
