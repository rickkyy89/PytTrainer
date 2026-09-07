"""Small Kivy smoke tests for the canvas adapter's paint ordering."""

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


kivy = pytest.importorskip("kivy")

from kivy.core.window import Window
from kivy.graphics import BorderImage, InstructionGroup, Line, RoundedRectangle
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

from kivy_app.material import ViewportMetrics, adaptive_profile
from kivy_app.theme import applica_tema


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_text_input_fill_precedes_native_cursor_and_focus_border_stays_above_content():
    profile = adaptive_profile(ViewportMetrics(400, 800))
    applica_tema(profile)

    field = TextInput(text="Squat")

    assert isinstance(field.canvas.before.children[0], InstructionGroup)
    borders = [item for item in field.canvas.after.children if isinstance(item, Line)]
    assert len(borders) == 1
    border = borders[0]
    normal_width = border.width

    field.focus = True

    assert border.width > normal_width


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_buttons_use_a_gradient_fill_and_darken_when_pressed():
    profile = adaptive_profile(ViewportMetrics(400, 800))
    applica_tema(profile)

    button = Button(text="Salva")
    fill = next(item for item in button.canvas.before.children if isinstance(item, RoundedRectangle))
    normal_texture = fill.texture

    button.state = "down"

    assert normal_texture is not None
    assert fill.texture is not normal_texture
    assert not any(isinstance(item, BorderImage) for item in button.canvas.children)
    assert button.background_color == pytest.approx((0.227, 0.600, 0.549, 1.0), abs=0.01)

    button.background_color = (1.0, 0.54, 0.48, 1.0)

    assert button.background_color == pytest.approx((1.0, 0.54, 0.48, 1.0))
