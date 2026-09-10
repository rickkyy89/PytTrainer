"""Headless tests for the shared compact menu (pure geometry + Kivy layer)."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

kivy = pytest.importorskip("kivy")

from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from kivy_app.compact_menu import (
    MenuAperto,
    Rect,
    altezza_lista_voci,
    altezza_popup_menu,
    apri_menu,
    dimensioni_menu,
    posizione_menu,
    rect_da,
    voce_menu,
)


def test_il_modulo_si_importa_senza_caricare_kivy():
    # I test headless e il main headless devono poter importare la politica
    # geometrica del menu senza toccare Kivy: gli import restano lazy.
    codice = ("import sys; import kivy_app.compact_menu, kivy_app.snackbar; "
              "assert 'kivy' not in sys.modules")
    subprocess.run([sys.executable, "-B", "-c", codice], cwd=PROJECT_ROOT,
                   check=True, capture_output=True)


def test_firma_apri_menu_compatibile_con_call_existing():
    import inspect

    parametri = list(inspect.signature(apri_menu).parameters)
    assert parametri == ["actions", "anchor"]
    assert inspect.signature(apri_menu).parameters["anchor"].default is None


def test_rect_da_normalizza_widget_stub_tuple_e_rect():
    da_widget = rect_da(SimpleNamespace(x=10, y=20, width=100, height=40))
    assert (da_widget.right, da_widget.top) == (110, 60)
    assert rect_da((0, 0, 5, 5)) == Rect(0, 0, 5, 5)
    assert rect_da(Rect(1, 2, 3, 4)) == Rect(1, 2, 3, 4)


def test_voce_menu_sceglie_sempre_un_preset_44_52_60():
    from kivy_app.material import BUTTON_HEIGHTS, pulsanti_correnti

    piccola, media, grande = sorted(BUTTON_HEIGHTS.values())
    assert (piccola, media, grande) == (44.0, 52.0, 60.0)  # la scala materiale
    assert voce_menu(piccola) == piccola   # pointer/compact: preset minimo
    assert voce_menu(40) == piccola
    assert voce_menu(48) == media          # touch standard
    assert voce_menu(media) == media
    assert voce_menu(53) == grande
    assert voce_menu(80) == grande         # capped at the largest preset
    # default: segue la gerarchia pulsanti scelta dall'utente
    assert voce_menu() == BUTTON_HEIGHTS[pulsanti_correnti()]


def test_dimensioni_menu_cresce_con_le_voci_resta_nel_viewport_e_diventa_scrollabile():
    _, alta, corta = dimensioni_menu(3, 400, 800)
    assert alta == 2 * 8 + 3 * voce_menu() + 2 * 4  # default row = preset
    assert not corta
    _, h_tanta, scrollabile = dimensioni_menu(80, 400, 800)
    assert h_tanta == 800 - 2 * 8
    assert scrollabile
    larga, _, _ = dimensioni_menu(3, 200, 800)  # viewport stretto: il menu si assottiglia
    assert larga == 200 - 2 * 8


def test_altezza_lista_voci_somma_padding_voci_e_spazi():
    assert altezza_lista_voci(0, 52) == 16
    assert altezza_lista_voci(1, 52) == 16 + 52
    assert altezza_lista_voci(3, 60) == 16 + 3 * 60 + 2 * 4
    assert altezza_lista_voci(2, 44, padding=0, spacing=8) == 96


def test_posizione_menu_kebab_allinea_a_destra_e_cade_sotto_l_ancora():
    # Konvenzione kebab: bordo destro del pannello all'ancora, sotto di essa
    # (in Kivy y cresce verso l'alto, quindi "sotto" = y minore).
    x, y = posizione_menu((300, 600, 48, 48), 280, 168, 400, 800)
    assert x == 348 - 280
    assert y == 600 - 4 - 168


def test_posizione_menu_si_ribalta_sopra_quando_sotto_non_c_e_spazio():
    x, y = posizione_menu((300, 100, 48, 48), 280, 168, 400, 800)
    assert y == 148 + 4  # ancora.top + offset
    assert x == 68       # allineamento a destra conservato


def test_posizione_menu_allinea_a_sinistra_se_all_destra_travalica():
    x, y = posizione_menu((30, 700, 48, 48), 280, 168, 400, 800)
    assert x == 30
    assert y == 700 - 4 - 168


def test_posizione_menu_non_esce_mai_dal_viewport():
    for ax, ay in [(0, 0), (399, 0), (0, 799), (399, 799)]:
        x, y = posizione_menu((ax, ay, 48, 48), 280, 168, 400, 800)
        assert 8 <= x and x + 280 <= 392
        assert 8 <= y and y + 168 <= 792


def test_altezza_popup_menu_usa_il_preset_e_limita_il_viewport():
    assert altezza_popup_menu(3, 800, voce=52) == 56 + (2 * 8 + 3 * 52 + 2 * 8)
    assert altezza_popup_menu(1, 800, voce=44) == 56 + (2 * 8 + 44)
    assert altezza_popup_menu(60, 800, voce=52) == 800 * 0.9  # bounded fallback


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_apri_menu_senza_anchor_ritorna_il_popup_storico_chiudibile_prima_del_callback():
    ordine = []
    popup = apri_menu((("Aggiorna", lambda: ordine.append("callback")),))
    assert isinstance(popup, Popup)
    popup.bind(on_pre_dismiss=lambda *_: ordine.append("dismiss"))
    bottoni = [w for w in popup.walk(restrict=True) if isinstance(w, Button)]
    assert [b.text for b in bottoni] == ["Aggiorna"]
    bottoni[0].dispatch("on_release")
    assert ordine == ["dismiss", "callback"]
    # cleanup: the fade-out animation needs a running Clock; detach at once
    popup.dismiss(animation=False)
    assert popup.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_apri_menu_senza_anchor_accetta_iteratori_e_limita_l_altezza():
    popup = apri_menu(iter([(f"Voce {i}", lambda i=i: None) for i in range(60)]))
    assert isinstance(popup, Popup)
    assert popup.height <= Window.height * 0.9 + 1
    assert any(isinstance(w, ScrollView) for w in popup.walk(restrict=True))
    popup.dismiss(animation=False)
    assert popup.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_menu_ancorato_rientra_nel_viewport_ed_e_scrollabile_con_tante_voci():
    azioni = tuple((f"Voce {i}", lambda i=i: None) for i in range(40))
    anchor = SimpleNamespace(x=Window.width - 60, y=Window.height - 60,
                             width=48, height=48)
    menu = apri_menu(azioni, anchor=anchor)
    assert isinstance(menu, MenuAperto)
    assert menu.overlay in Window.children
    pannello = menu.pannello
    assert pannello.x >= 0 and pannello.y >= 0
    assert pannello.right <= Window.width + 1 and pannello.top <= Window.height + 1
    assert any(isinstance(w, ScrollView) for w in menu.overlay.walk(restrict=True))
    menu.dismiss()
    assert menu.overlay.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_il_preset_delle_voci_e_uniforme_tra_popup_e_menu_ancorato():
    # Stesso preset 44/52/60 dp (convertito una sola volta con dp()) in
    # entrambe le renderizzazioni, senza confronti dp/pixel.
    from kivy.metrics import dp

    from kivy_app.material import profile_for_window

    atteso = dp(voce_menu(profile_for_window(Window).touch_target))
    assert atteso in (dp(44.0), dp(52.0), dp(60.0))
    azioni = (("A", lambda: None), ("B", lambda: None))

    popup = apri_menu(azioni)
    bottoni = [w for w in popup.walk(restrict=True) if isinstance(w, Button)]
    assert len(bottoni) == 2
    assert all(b.height == pytest.approx(atteso) for b in bottoni)
    popup.dismiss(animation=False)

    menu = apri_menu(azioni, anchor=(Window.width - 80, Window.height - 60, 48, 48))
    bottoni = [w for w in menu.overlay.walk(restrict=True) if isinstance(w, Button)]
    assert all(b.height == pytest.approx(atteso) for b in bottoni)
    menu.dismiss()
    assert menu.overlay.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_menu_ancorato_chiude_prima_di_invocare_il_callback():
    riferimento = {}
    chiusi = []

    def callback():
        chiusi.append(riferimento["menu"].overlay.parent is None)

    menu = apri_menu([("Chiudi", callback)],
                     anchor=(10, Window.height - 60, 48, 48))
    riferimento["menu"] = menu
    bottoni = [w for w in menu.overlay.walk(restrict=True) if isinstance(w, Button)]
    bottoni[0].dispatch("on_release")
    assert chiusi == [True]
    assert menu.overlay.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_menu_ancorato_un_tocco_fuori_dal_pannello_lo_chiude():
    menu = apri_menu([("A", lambda: None)], anchor=(10, 10, 48, 48))
    tocco = SimpleNamespace(pos=(Window.width - 2, 2))
    assert menu.overlay.on_touch_down(tocco) is True
    assert menu.overlay.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_menu_ancorato_dismiss_idempotente():
    menu = apri_menu([("A", lambda: None)], anchor=(Window.width // 2,
                                                    Window.height // 2, 48, 48))
    menu.dismiss()
    menu.dismiss()
    assert menu.overlay.parent is None
