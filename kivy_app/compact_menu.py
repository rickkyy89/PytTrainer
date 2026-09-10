"""Compact global actions menu used by secondary Kivy screens.

The sizing/placement policy is pure Python and Kivy-free at import time so
headless tests can exercise it and ``kivy_app`` stays importable on machines
without a display.  The widget layer at the bottom imports Kivy lazily,
inside the builders.

Row heights come from the shared button preset ladder owned by
``kivy_app.material`` (``BUTTON_HEIGHTS``: 44/52/60 dp); :func:`voce_menu`
maps the profile's touch target onto it.  Both the anchored menu and the
popup fallback compute their rows in dp and convert with ``dp()`` exactly
once at the Kivy boundary, so dp and pixels are never compared against each
other.

``apri_menu(actions, anchor=None)`` is backward compatible: without an
anchor it opens the historic centred popup (height-bounded to the
viewport); with an anchor it renders a real kebab-style dropdown clamped to
the viewport and scrollable when the action list is long.
"""

from __future__ import annotations

from dataclasses import dataclass

from .material import BUTTON_HEIGHTS, pulsanti_correnti

# Row-height presets (dp) shared by the anchored menu and the popup fallback.
# The ladder itself lives in ``material.BUTTON_HEIGHTS`` (single source of
# truth); this module only orders it and maps targets onto it.
MENU_PRESET_DP = tuple(sorted(BUTTON_HEIGHTS.values()))

# Kebab menu geometry, in dp; the widget layer converts with ``dp()``.
MENU_LARGHEZZA_DP = 280.0
MENU_SPACING_DP = 4.0
MENU_PADDING_DP = 8.0
MENU_OFFSET_DP = 4.0
MENU_BORDO_DP = 8.0

# Historic centred-popup geometry (kept for the no-anchor fallback).
POPUP_TITOLO_DP = 56.0
POPUP_SPACING_DP = 8.0
POPUP_PADDING_DP = 8.0
POPUP_FRAZIONE_ALTEZZA = 0.9


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in window coordinates (Kivy: ``y`` is the bottom)."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height


def rect_da(anchor) -> Rect:
    """Normalize an anchor: a ``Rect``, an ``(x, y, w, h)`` sequence or a widget.

    Attached widgets are resolved to window coordinates through
    ``to_window()``; duck-typed stand-ins exposing plain ``x/y/width/height``
    (SimpleNamespace in headless tests) work too.
    """
    if isinstance(anchor, Rect):
        return anchor
    if isinstance(anchor, (tuple, list)):
        x, y, width, height = anchor
        return Rect(float(x), float(y), float(width), float(height))
    if hasattr(anchor, "to_window"):
        x, y = anchor.to_window(anchor.x, anchor.y)
    else:
        x, y = anchor.x, anchor.y
    return Rect(float(x), float(y), float(anchor.width), float(anchor.height))


def clampa(valore: float, minimo: float, massimo: float) -> float:
    """Clamp ``valore`` into ``[minimo, massimo]``; an inverted range yields ``minimo``."""
    if massimo < minimo:
        return minimo
    return max(minimo, min(valore, massimo))


def voce_menu(target_dp: float | None = None) -> float:
    """Row height: the smallest 44/52/60 dp preset that fits the touch target.

    ``None`` selects the user's current button hierarchy
    (``material.pulsanti_correnti``), which is also what every profile's
    ``touch_target`` resolves to, so menu rows land on the exact preset.  The
    value is logical dp; callers converting for Kivy must apply ``dp()``
    exactly once (never mix with pixel measures).
    """
    if target_dp is None:
        return BUTTON_HEIGHTS[pulsanti_correnti()]
    for altezza in MENU_PRESET_DP:
        if target_dp <= altezza:
            return altezza
    return MENU_PRESET_DP[-1]


def altezza_lista_voci(quante_voci, voce, *, padding=MENU_PADDING_DP,
                       spacing=MENU_SPACING_DP):
    """Natural height of a vertical list of rows (all values share one unit)."""
    return 2 * padding + quante_voci * voce + max(quante_voci - 1, 0) * spacing


def dimensioni_menu(quante_voci, larghezza_vp, altezza_vp, *,
                    voce=None, larghezza=MENU_LARGHEZZA_DP,
                    padding=MENU_PADDING_DP, spacing=MENU_SPACING_DP,
                    bordo=MENU_BORDO_DP):
    """Return ``(width, height, scrollable)`` for a kebab action list.

    All numbers share the unit the caller provides (dp or px).  ``voce=None``
    selects the current row preset via :func:`voce_menu`.  The panel is
    never larger than the viewport minus ``bordo`` on each side; a list that
    would overflow the viewport is capped and flagged ``scrollable``.
    """
    voce = voce_menu() if voce is None else voce
    larghezza_ok = max(larghezza_vp - 2 * bordo, 0.0)
    altezza_massima = max(altezza_vp - 2 * bordo, 0.0)
    naturale = altezza_lista_voci(quante_voci, voce, padding=padding, spacing=spacing)
    return (min(larghezza, larghezza_ok),
            min(naturale, altezza_massima),
            naturale > altezza_massima)


def posizione_menu(anchor, larghezza, altezza, larghezza_vp, altezza_vp, *,
                   offset=MENU_OFFSET_DP, bordo=MENU_BORDO_DP):
    """Return the ``(x, y)`` for a panel hanging from ``anchor`` (kebab style).

    The panel's right edge aligns with the anchor's right edge and it drops
    *below* the anchor (Kivy's y axis grows upward).  When right alignment
    would cross the left viewport edge the panel left-aligns on the anchor,
    and when there is no room below but plenty above it flips above.  The
    result is always clamped inside the viewport with ``bordo`` of margin.
    """
    a = rect_da(anchor)
    x = a.right - larghezza
    if x < bordo:
        x = a.x
    y = a.y - offset - altezza
    if y < bordo and a.top + offset + altezza <= altezza_vp - bordo:
        y = a.top + offset
    return (clampa(x, bordo, max(larghezza_vp - larghezza - bordo, bordo)),
            clampa(y, bordo, max(altezza_vp - altezza - bordo, bordo)))


def altezza_popup_menu(quante_voci, altezza_vp, *, voce=None, titolo=POPUP_TITOLO_DP,
                      padding=POPUP_PADDING_DP, spacing=POPUP_SPACING_DP,
                      frazione=POPUP_FRAZIONE_ALTEZZA):
    """Bounded height for the centred fallback popup (same unit in).

    Built from the real geometry (title + padded row list) so both renderers
    honor the same 44/52/60 dp preset passed as ``voce``.
    """
    voce = voce_menu() if voce is None else voce
    naturale = titolo + altezza_lista_voci(quante_voci, voce,
                                           padding=padding, spacing=spacing)
    return min(naturale, altezza_vp * frazione)


@dataclass(frozen=True)
class MenuAperto:
    """Handle for an open anchored menu; ``dismiss()`` is idempotent."""

    overlay: object
    pannello: object
    chiudi: object

    def dismiss(self) -> None:
        self.chiudi()


def apri_menu(actions, anchor=None):
    """Open a small touch-friendly menu for global actions.

    ``actions`` is an iterable of ``(label, callback)`` pairs. The menu is
    dismissed before invoking the callback so actions that rebuild the root
    screen cannot leave an orphaned overlay behind.

    Without ``anchor`` the historic centred ``Popup`` is returned (a safe
    bounded fallback for any screen). With an anchor — a kebab button widget,
    an ``(x, y, w, h)`` rect or a :class:`Rect` — a :class:`MenuAperto`
    overlay is returned, placed kebab-style by the anchor, constrained to
    the viewport and scrollable when the list is long.  Both variants share
    the same row preset (:func:`voce_menu`) and touch-friendly sizing.
    """
    azioni = list(actions)
    if anchor is None:
        return _apri_menu_centrale(azioni)
    return _apri_menu_ancorato(azioni, anchor)


def _apri_menu_centrale(azioni):
    """Historic centred popup, now bounded to the viewport with a scroll fallback."""
    from kivy.core.window import Window
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    from .material import profile_for_window

    voce = dp(voce_menu(profile_for_window(Window).touch_target))
    content = BoxLayout(orientation="vertical", spacing=dp(POPUP_SPACING_DP),
                        padding=dp(POPUP_PADDING_DP))
    naturale = dp(POPUP_TITOLO_DP) + altezza_lista_voci(
        len(azioni), voce, padding=dp(POPUP_PADDING_DP), spacing=dp(POPUP_SPACING_DP))
    altezza = min(naturale, Window.height * POPUP_FRAZIONE_ALTEZZA)
    if altezza < naturale:  # tiny viewport: keep every action reachable
        content.size_hint_y = None
        content.bind(minimum_height=content.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(content)
        popup = Popup(title="Menu", content=scroll, size_hint=(0.72, None),
                      height=altezza, auto_dismiss=True)
    else:
        popup = Popup(title="Menu", content=content, size_hint=(0.72, None),
                      height=altezza, auto_dismiss=True)
    for label, callback in azioni:
        button = Button(text=label, size_hint_y=None, height=voce)
        button.bind(on_release=lambda *_args, cb=callback: (popup.dismiss(), cb()))
        content.add_widget(button)
    popup.open()
    return popup


def _apri_menu_ancorato(azioni, anchor):
    """Render the kebab dropdown as a touch-absorbing overlay on the Window."""
    from kivy.core.window import Window
    from kivy.graphics import Color, Rectangle
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.scrollview import ScrollView

    from .material import hex_to_rgba, profile_for_window

    profile = profile_for_window(Window)
    bordo = dp(MENU_BORDO_DP)
    voce = dp(voce_menu(profile.touch_target))  # dp -> px once, no unit mixing
    larghezza, altezza, _scrollabile = dimensioni_menu(
        len(azioni), Window.width, Window.height, voce=voce,
        larghezza=dp(MENU_LARGHEZZA_DP), padding=dp(MENU_PADDING_DP),
        spacing=dp(MENU_SPACING_DP), bordo=bordo)
    x, y = posizione_menu(anchor, larghezza, altezza, Window.width, Window.height,
                          offset=dp(MENU_OFFSET_DP), bordo=bordo)

    stato = {"chiuso": False}

    def chiudi(*_):
        if stato["chiuso"]:
            return
        stato["chiuso"] = True
        if overlay.parent is not None:
            overlay.parent.remove_widget(overlay)

    pannello = BoxLayout(orientation="vertical", size_hint=(None, None),
                         size=(larghezza, altezza), pos=(x, y),
                         padding=dp(MENU_PADDING_DP), spacing=dp(MENU_SPACING_DP))
    with pannello.canvas.before:
        Color(*hex_to_rgba(profile.tokens.colors["surface_container"], 0.98))
        fondo = Rectangle(pos=pannello.pos, size=pannello.size)
    pannello.bind(pos=lambda *_: setattr(fondo, "pos", pannello.pos),
                  size=lambda *_: setattr(fondo, "size", pannello.size))

    elenco = BoxLayout(orientation="vertical", size_hint_y=None,
                       spacing=dp(MENU_SPACING_DP))
    elenco.bind(minimum_height=elenco.setter("height"))
    for label, callback in azioni:
        button = Button(text=label, size_hint_y=None, height=voce)
        button.bind(on_release=lambda *_args, cb=callback: (chiudi(), cb()))
        elenco.add_widget(button)
    scroll = ScrollView(size_hint=(1, 1))
    scroll.add_widget(elenco)
    pannello.add_widget(scroll)

    class _OverlayMenu(FloatLayout):
        """Full-window layer: taps outside the panel dismiss the menu."""

        def on_touch_down(self, touch):
            if pannello.collide_point(*touch.pos):
                return super().on_touch_down(touch)
            chiudi()
            return True

    overlay = _OverlayMenu(size_hint=(1, 1))
    overlay.add_widget(pannello)
    Window.add_widget(overlay)
    return MenuAperto(overlay=overlay, pannello=pannello, chiudi=chiudi)
