"""Headless tests for the fine-drag scrub slider (no rendering needed)."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


kivy = pytest.importorskip("kivy")

from kivy_app.fine_slider import FineSlider


class Touch(SimpleNamespace):
    # Kivy reuses the same touch object for down/move/up; this mutable stand-in
    # lets a test simulate one gesture by updating .x / .pos in place.
    def __init__(self, x, y=20):
        super().__init__(x=x, y=y, pos=(x, y))

    def set(self, x, y=20):
        self.x = x
        self.y = y
        self.pos = (x, y)
        return self


def make_slider(minimum=0, maximum=1200, width=400):
    slider = FineSlider(min=minimum, max=maximum, value=0)
    slider.size = (width, 40)
    slider.pos = (0, 0)
    return slider


def test_tap_salta_linealmente_sulla_posizione():
    slider = make_slider()
    touch = Touch(300)

    slider.on_touch_down(touch)
    slider.on_touch_up(touch)

    # 300 su 400 px = 0.75 dell'intervallo 1200s = 900s
    assert slider.value == pytest.approx(900.0)


def test_drag_sensibilita_ridotta_per_piccoli_spostamenti():
    slider = make_slider()
    touch = Touch(100)

    slider.on_touch_down(touch)           # press a 100px = 300s
    touch.set(112)
    slider.on_touch_move(touch)
    touch.set(140)
    slider.on_touch_move(touch)

    # delta 40px/400 * 1200 * 0.10 = 12s di movimento fine (non un salto a 420s)
    assert slider.value == pytest.approx(300.0 + 12.0, abs=0.2)


def test_drag_piccolissimo_sotto_soglia_resta_un_tap_che_salta():
    slider = make_slider()
    touch = Touch(300)

    slider.on_touch_down(touch)
    touch.set(301)  # sotto la soglia: non e' un drag
    slider.on_touch_move(touch)
    slider.on_touch_up(touch)

    # si comporta come un tap -> salto lineare
    assert slider.value == pytest.approx(900.0)


def test_drag_clampa_al_limite_superiore():
    slider = make_slider()
    touch = Touch(0)

    slider.on_touch_down(touch)   # press all'inizio barra (0s)
    touch.set(6000)               # ben oltre la larghezza della barra
    slider.on_touch_move(touch)

    # con fattore 0.1 un delta enorme supererebbe l'intervallo -> clamp al max
    assert slider.value == pytest.approx(slider.max)


def test_drag_negativo_scende_sotto_il_valore_di_pressione():
    slider = make_slider()
    touch = Touch(200)

    slider.on_touch_down(touch)   # 600s
    touch.set(160)
    slider.on_touch_move(touch)   # -40px -> -12s

    assert slider.value == pytest.approx(588.0, abs=0.2)
