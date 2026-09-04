"""Kivy adapter that paints the Material tokens onto the default widgets.

The token *values* live in :mod:`kivy_app.material` (headless, tested); this
module is the only place allowed to touch Kivy class-level styles, so screens
never set colors or fonts of their own.
"""

from __future__ import annotations

from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from .material import UiProfile, hex_to_rgba


def applica_tema(profile: UiProfile) -> None:
    """Apply the dark Material theme derived from the current profile."""
    colors = profile.tokens.colors
    Window.clearcolor = hex_to_rgba(colors["background"])
    # Keep the focused field above the virtual keyboard on Android (no-op on
    # desktop), so the fixed bottom action bar never becomes unreachable.
    Window.softinput_mode = "below_target"
    Button.background_normal = ""
    Button.background_color = hex_to_rgba(colors["surface_variant"])
    Button.color = hex_to_rgba(colors["text"])
    Label.color = hex_to_rgba(colors["text"])
    TextInput.background_color = hex_to_rgba(colors["surface"])
    TextInput.foreground_color = hex_to_rgba(colors["text"])
    TextInput.hint_text_color = hex_to_rgba(colors["muted"])
    TextInput.cursor_color = hex_to_rgba(colors["accent"])
    ScrollView.bar_color = (0, 0, 0, 0)
    Popup.separator_color = hex_to_rgba(colors["surface_variant"])
