"""Small Kivy smoke tests for the canvas adapter's paint ordering."""

import pytest


kivy = pytest.importorskip("kivy")

from kivy.core.window import Window
from kivy.graphics import InstructionGroup, Line
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
