"""Kivy adapter that paints the Material tokens onto the default widgets.

The token *values* live in :mod:`kivy_app.material` (headless, tested); this
module is the only place allowed to touch Kivy class-level styles, so screens
never set colors or fonts of their own.
"""

from __future__ import annotations

from kivy.core.window import Window
from kivy.graphics import Color, InstructionGroup, Line, RoundedRectangle
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.metrics import dp, sp

from .material import UiProfile, hex_to_rgba


def _imposta_default_font(cls, nome: str, valore: float) -> None:
    """Retune a widget-class font default without clobbering the descriptor.

    ``cls.font_size = 12.0`` replaces the Kivy Property descriptor on the
    class with a plain float, which later crashes ``EventDispatcher.__cinit__``
    ("Cannot convert float to kivy.properties.Property") and silently stores
    raw values that skip unit parsing. Writing the descriptor's own
    ``defaultvalue`` keeps the property machinery intact.
    """
    owner = next(c for c in cls.__mro__ if nome in c.__dict__)
    owner.__dict__[nome].defaultvalue = valore


def _control_color(widget, *, pressed=False, disabled=False):
    """Return a state color while retaining the widget's local color choice."""
    red, green, blue, alpha = widget.background_color
    if pressed:
        red, green, blue = red * 0.78, green * 0.78, blue * 0.78
    if disabled:
        alpha *= 0.45
    return red, green, blue, alpha


def _paint_button(button, profile) -> None:
    radius = dp(profile.tokens.dimensions["control_radius"])
    border = dp(profile.tokens.dimensions["border_width"])
    instructions = button.canvas.before
    fill = Color(*_control_color(button))
    shape = RoundedRectangle(pos=button.pos, size=button.size, radius=[(radius, radius)])
    outline = Color(*_control_color(button))
    line = Line(rounded_rectangle=(button.x, button.y, button.width, button.height, radius),
                width=border)
    instructions.add(fill)
    instructions.add(shape)
    instructions.add(outline)
    instructions.add(line)

    def redraw(*_):
        fill.rgba = _control_color(button, pressed=button.state == "down",
                                   disabled=button.disabled)
        outline.rgba = _control_color(button, disabled=button.disabled)
        shape.pos = button.pos
        shape.size = button.size
        line.rounded_rectangle = (button.x, button.y, button.width, button.height, radius)

    button.bind(pos=redraw, size=redraw, background_color=redraw,
                state=redraw, disabled=redraw)
    redraw()


def _paint_text_input(field, profile) -> None:
    radius = dp(profile.tokens.dimensions["control_radius"])
    normal_width = dp(profile.tokens.dimensions["border_width"])
    focus_width = dp(profile.tokens.dimensions["focus_border_width"])
    # TextInput's default KV rule already placed its background and cursor in
    # canvas.before.  Insert our opaque fill at index zero, then put only the
    # outline in canvas.after: the fill cannot cover the native cursor and the
    # border remains visible above the dynamically rebuilt text canvas.
    fill_instructions = InstructionGroup()
    fill = Color(*hex_to_rgba(profile.tokens.colors["surface"]))
    shape = RoundedRectangle(pos=field.pos, size=field.size, radius=[(radius, radius)])
    fill_instructions.add(fill)
    fill_instructions.add(shape)
    field.canvas.before.insert(0, fill_instructions)

    outline = Color(*hex_to_rgba(profile.tokens.colors["muted"], 0.65))
    line = Line(rounded_rectangle=(field.x, field.y, field.width, field.height, radius),
                width=normal_width)
    field.canvas.after.add(outline)
    field.canvas.after.add(line)

    def redraw(*_):
        line.width = focus_width if field.focus else normal_width
        outline.rgba = hex_to_rgba(
            profile.tokens.colors["focus"] if field.focus else profile.tokens.colors["muted"],
            1.0 if field.focus else 0.65,
        )
        shape.pos = field.pos
        shape.size = field.size
        line.rounded_rectangle = (field.x, field.y, field.width, field.height, radius)

    field.bind(pos=redraw, size=redraw, focus=redraw)
    redraw()


def _installa_pittura_controlli(profile: UiProfile) -> None:
    """Install canvas adapters once; normal Button/TextInput need no screen edits."""
    if not getattr(Button, "_pytrainer_theme_adapter", False):
        original_button_init = Button.__init__

        def button_init(button, *args, **kwargs):
            original_button_init(button, *args, **kwargs)
            _paint_button(button, Button._pytrainer_theme_profile)

        Button.__init__ = button_init
        Button._pytrainer_theme_adapter = True
    if not getattr(TextInput, "_pytrainer_theme_adapter", False):
        original_input_init = TextInput.__init__

        def input_init(field, *args, **kwargs):
            original_input_init(field, *args, **kwargs)
            _paint_text_input(field, TextInput._pytrainer_theme_profile)

        TextInput.__init__ = input_init
        TextInput._pytrainer_theme_adapter = True
    Button._pytrainer_theme_profile = profile
    TextInput._pytrainer_theme_profile = profile


def applica_tema(profile: UiProfile) -> None:
    """Apply the dark Material theme derived from the current profile."""
    colors = profile.tokens.colors
    Window.clearcolor = hex_to_rgba(colors["background"])
    # Keep the focused field above the virtual keyboard on Android (no-op on
    # desktop), so the fixed bottom action bar never becomes unreachable.
    Window.softinput_mode = "below_target"
    Button.background_normal = ""
    Button.background_down = ""
    Button.background_color = hex_to_rgba(colors["surface_variant"])
    Button.color = hex_to_rgba(colors["text"])
    Label.color = hex_to_rgba(colors["text"])
    TextInput.background_color = hex_to_rgba(colors["surface"])
    TextInput.background_normal = ""
    TextInput.background_active = ""
    TextInput.foreground_color = hex_to_rgba(colors["text"])
    TextInput.hint_text_color = hex_to_rgba(colors["muted"])
    TextInput.cursor_color = hex_to_rgba(colors["accent"])
    ScrollView.bar_color = (0, 0, 0, 0)
    Popup.separator_color = hex_to_rgba(colors["surface_variant"])
    CheckBox.active_color = hex_to_rgba(colors["accent"])
    CheckBox.background_color = (1, 1, 1, 0.8)
    body = sp(profile.tokens.typography["body"])
    _imposta_default_font(Button, "font_size", body)
    _imposta_default_font(Label, "font_size", body)
    _imposta_default_font(TextInput, "font_size", body)
    _imposta_default_font(Popup, "title_size", sp(profile.tokens.typography["section"]))
    _installa_pittura_controlli(profile)


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
