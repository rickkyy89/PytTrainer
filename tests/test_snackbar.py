"""Headless tests for the shared snackbar (pure geometry + Kivy layer)."""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

kivy = pytest.importorskip("kivy")

from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from kivy_app.compact_menu import Rect
from kivy_app.snackbar import (
    SnackAperto,
    altezza_barra_inferiore,
    larghezza_snackbar,
    mostra_snackbar,
    posizione_snackbar,
)


def test_firma_mostra_snackbar_esatta():
    import inspect

    parametri = inspect.signature(mostra_snackbar).parameters
    assert list(parametri) == ["parent", "testo", "durata"]
    assert parametri["durata"].default == 3.0


def test_altezza_barra_riconosce_l_ultimo_figlio_ad_altezza_fissa():
    # Kivy tiene i figli in ordine inverso di aggiunta: children[0] e' la
    # barra inferiore Aggiunta per ultima dalle schermate reali.
    barra = SimpleNamespace(x=0, y=0, width=400, height=54, size_hint_y=None)
    scroll = SimpleNamespace(x=0, y=54, width=400, height=546, size_hint_y=1)
    genitore = SimpleNamespace(x=0, y=0, width=400, height=600,
                               orientation="vertical", spacing=[6, 6],
                               children=[barra, scroll])
    assert altezza_barra_inferiore(genitore) == 60  # barra.top + spacing


def test_altezza_barra_scende_nello_stack_di_schermate():
    # Passando la navigazione (stack) invece della schermata, la ricerca
    # scende nei contenitori riempitivi fino alla barra fissata in basso.
    barra = SimpleNamespace(x=0, y=0, width=400, height=48, size_hint_y=None)
    corpo = SimpleNamespace(x=0, y=48, width=400, height=552, size_hint_y=1)
    schermata = SimpleNamespace(x=0, y=0, width=400, height=600,
                                orientation="vertical", spacing=[6, 6],
                                children=[barra, corpo])
    precedente = SimpleNamespace(x=0, y=0, width=400, height=600, size_hint_y=1)
    stack = SimpleNamespace(x=0, y=0, width=400, height=600,
                            orientation="vertical", spacing=0,
                            children=[schermata, precedente])
    assert altezza_barra_inferiore(stack) == 54  # 48 + spacing della schermata
    assert altezza_barra_inferiore(schermata) == 54


def test_contenuto_fisso_ma_ingombrante_non_viene_reso_comme_barra():
    # Un contenuto scrollabile con size_hint_y=None (min_height legato) non
    # deve essere scambiato per una barra: e' piu' meta' del contenitore.
    contenuto = SimpleNamespace(x=0, y=0, width=400, height=1100,
                                size_hint_y=None, children=[])
    genitore = SimpleNamespace(x=0, y=0, width=400, height=600,
                               orientation="vertical", spacing=0,
                               children=[contenuto])
    assert altezza_barra_inferiore(genitore) == 0.0


def test_altezza_barra_zero_senza_barra_reale():
    riempitivo = SimpleNamespace(x=0, y=0, width=400, height=600, size_hint_y=1)
    assert altezza_barra_inferiore(
        SimpleNamespace(x=0, y=0, width=400, height=600, orientation="vertical",
                        spacing=0, children=[riempitivo])) == 0.0
    assert altezza_barra_inferiore(
        SimpleNamespace(orientation="horizontal", spacing=0,
                        children=[SimpleNamespace(x=0, y=0, width=400,
                                                  height=48, size_hint_y=None)])) == 0.0
    assert altezza_barra_inferiore(
        SimpleNamespace(orientation="vertical", spacing=0, children=[])) == 0.0
    assert altezza_barra_inferiore(None) == 0.0


def test_larghezza_snackbar_limitata_entro_il_viewport():
    assert larghezza_snackbar(1000) == 480
    assert larghezza_snackbar(300) == 300 - 2 * 16
    assert larghezza_snackbar(20) == 0


def test_posizione_snackbar_centra_sul_genitore_e_sorvola_la_barra():
    x, y = posizione_snackbar(Rect(100, 0, 400, 600), 300, 48, 800, 600, barra_h=60)
    assert x == 150          # centered on the parent's 400-wide area
    assert y == 60 + 16      # above the bar, plus the bottom margin


def test_posizione_snackbar_resta_sempre_nel_viewport():
    x, y = posizione_snackbar(Rect(0, 500, 800, 100), 300, 48, 800, 600, barra_h=80)
    assert y == 600 - 48 - 16  # would overflow: clamped back inside
    x, y = posizione_snackbar(Rect(700, 0, 100, 600), 300, 48, 800, 600)
    assert x == 800 - 300 - 16  # parent near the right edge: clamp horizontally


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_snackbar_reale_si_posiziona_sopra_la_barra_inferiore():
    genitore = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
    genitore.size = (Window.width, Window.height)
    genitore.pos = (0, 0)
    genitore.add_widget(BoxLayout())  # scrolling content (fills the space)
    barra = BoxLayout(size_hint_y=None, height=dp(48))
    genitore.add_widget(barra)
    assert altezza_barra_inferiore(genitore) >= barra.height  # heuristic on real Kivy

    snack = mostra_snackbar(genitore, "Fatto", durata=30)
    assert isinstance(snack, SnackAperto)
    assert snack.pannello.y > barra.top  # floats above the action bar
    snack.dismiss()
    assert snack.overlay.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_snackbar_passando_lo_stack_sorvola_la_barra_della_schermata():
    # Main shows snackbars over the navigation stack (self.stack), not the
    # screen: the snack must still clear the screen's fixed action bar.
    stack = BoxLayout(orientation="vertical")
    stack.size = (Window.width, Window.height)
    stack.pos = (0, 0)
    schermata = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
    schermata.add_widget(BoxLayout())  # scrolling content
    barra = BoxLayout(size_hint_y=None, height=dp(48))
    schermata.add_widget(barra)
    stack.add_widget(schermata)
    assert schermata in stack.children

    snack = mostra_snackbar(stack, "Scheda eliminata.", durata=30)
    assert snack.pannello.y > barra.top
    snack.dismiss()
    assert snack.overlay.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_snackbar_mostra_il_testo_e_si_autosclude():
    from kivy.clock import Clock

    snack = mostra_snackbar(BoxLayout(), "Salvato", durata=0.1)
    assert snack.overlay in Window.children
    etichette = [w for w in snack.overlay.walk(restrict=True) if isinstance(w, Label)]
    assert any(l.text == "Salvato" for l in etichette)
    time.sleep(0.3)
    Clock.tick()
    assert snack.overlay.parent is None


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_mostra_snackbar_sostituisce_quella_precedente_senza_accumularsi():
    base = len(Window.children)
    prima = mostra_snackbar(BoxLayout(), "una", durata=30)
    assert len(Window.children) == base + 1
    seconda = mostra_snackbar(BoxLayout(), "due", durata=30)
    assert prima.overlay.parent is None  # replaced, not stacked
    assert len(Window.children) == base + 1
    assert seconda.overlay in Window.children
    seconda.dismiss()
    assert len(Window.children) == base


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_snackbar_dismiss_idempotente_e_parent_none_sicuro():
    base = len(Window.children)
    snack = mostra_snackbar(None, "centrato sulla finestra", durata=30)
    assert snack.overlay in Window.children
    assert snack.pannello.x >= 0 and snack.pannello.right <= Window.width + 1
    snack.dismiss()
    snack.dismiss()  # idempotent: no error, no double removal
    assert snack.overlay.parent is None
    assert len(Window.children) == base
