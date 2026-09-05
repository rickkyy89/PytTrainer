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
from kivy.metrics import sp

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
    Button.font_size = sp(profile.tokens.typography["label"])
    Label.font_size = sp(profile.tokens.typography["body"])
    TextInput.font_size = sp(profile.tokens.typography["body"])
    Popup.title_size = sp(profile.tokens.typography["section"])


def configura_tema_md(theme_cls, profile: UiProfile) -> None:
    """Bridge token-owned colors to KivyMD without enabling dynamic colors."""
    theme_cls.theme_style = "Dark"
    theme_cls.dynamic_color = False
    theme_cls.primary_palette = profile.tokens.colors["primary"]
    theme_cls.set_colors()


def aggiorna_testo_widget(root, profile: UiProfile) -> None:
    """Apply a text preference in-place, preserving editor and workout state."""
    body = sp(profile.tokens.typography["body"])
    label = sp(profile.tokens.typography["label"])
    for widget in [root, *list(root.walk(restrict=True))]:
        if isinstance(widget, TextInput):
            widget.font_size = body
        elif isinstance(widget, Button):
            widget.font_size = label
        elif isinstance(widget, Label):
            widget.font_size = body
