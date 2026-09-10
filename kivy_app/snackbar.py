"""In-app transient messages (snackbars) for the Kivy screens.

``mostra_snackbar(parent, testo, durata=3.0)`` floats a small dark strip
over the running screen — centred horizontally on ``parent`` and lifted
above its fixed bottom bar when one is detected (the search descends
filling containers, so passing the navigation stack works like passing the
screen itself) — then removes it after ``durata`` seconds. The strip is
added to the Window as a pass-through overlay, so it never steals layout
space nor blocks input.

The geometry helpers are Kivy-free and duck-typed (headless-testable); Kivy
is imported lazily inside the builder, mirroring ``compact_menu``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .compact_menu import Rect, clampa, rect_da

# Geometry in dp; the widget layer converts with ``dp()``.
SNACK_LARGHEZZA_MAX_DP = 480.0
SNACK_ALTEZZA_DP = 48.0
SNACK_BORDO_DP = 16.0
SNACK_BARRA_FRAZIONE_MAX = 0.5  # a bar is thin: at most half its container


def _spacing(layout) -> float:
    valore = getattr(layout, "spacing", 0) or 0
    if isinstance(valore, (list, tuple)):
        valore = valore[1] if len(valore) > 1 else valore[0]
    return float(valore)


def altezza_barra_inferiore(parent) -> float:
    """Return the bottom inset reserved by a fixed action bar, else 0.0.

    A screen's last-added child is its action/timer bar with
    ``size_hint_y=None`` (Kivy stores children in reverse add order), but
    callers may pass the navigation stack instead of the screen itself, in
    which case the bottom-most child is the filling screen container.  The
    search therefore descends filling containers until it finds a *thin*
    fixed-height child, and measures that bar's top edge geometrically from
    ``parent``'s bottom edge — so the snack clears the real bar whichever
    ancestor it is shown over.  Duck-typed (plain stand-ins work in headless
    tests) and deliberately conservative: 0.0 when nothing matches.
    """
    base = None
    livello = parent
    for _ in range(16):  # layout chains stay shallow; never loop forever
        if getattr(livello, "orientation", None) != "vertical":
            return 0.0
        figli = getattr(livello, "children", None) or ()
        if not figli:
            return 0.0
        barra = figli[0]
        try:
            rect_livello = rect_da(livello)
            rect_barra = rect_da(barra)
        except (AttributeError, TypeError, ValueError):
            return 0.0
        fissa = getattr(barra, "size_hint_y", None) is None
        sottile = 0 < rect_barra.height <= SNACK_BARRA_FRAZIONE_MAX * rect_livello.height
        if fissa and sottile:
            if base is None:
                try:
                    base = rect_da(parent).y
                except (AttributeError, TypeError, ValueError):
                    return 0.0
            inset = rect_barra.top - base + _spacing(livello)
            return inset if inset > 0 else 0.0
        livello = barra
    return 0.0


def larghezza_snackbar(larghezza_vp, *, massimo=SNACK_LARGHEZZA_MAX_DP,
                       bordo=SNACK_BORDO_DP):
    """Snack width capped at ``massimo``, never wider than viewport - 2*bordo."""
    return min(massimo, max(larghezza_vp - 2 * bordo, 0.0))


def posizione_snackbar(parent, larghezza, altezza, larghezza_vp, altezza_vp,
                       barra_h=0.0, *, bordo=SNACK_BORDO_DP):
    """Return ``(x, y)`` centering the snack on ``parent``, above its bar.

    The snack sits ``bordo`` pixels above the detected bottom bar (or the
    parent's bottom edge) and is clamped to stay fully inside the viewport.
    """
    p = rect_da(parent)
    x = clampa(p.x + (p.width - larghezza) / 2.0,
               bordo, max(larghezza_vp - larghezza - bordo, bordo))
    y = clampa(p.y + barra_h + bordo, bordo, max(altezza_vp - altezza - bordo, bordo))
    return x, y


@dataclass(frozen=True)
class SnackAperto:
    """Handle for a visible snack; ``dismiss()`` is idempotent."""

    overlay: object
    pannello: object
    chiudi: object

    def dismiss(self) -> None:
        self.chiudi()


_snack_corrente: SnackAperto | None = None


def mostra_snackbar(parent, testo, durata=3.0):
    """Show ``testo`` transiently (info/success feedback) over ``parent``.

    The snack auto-dismisses after ``durata`` seconds and showing a new one
    replaces the previous, so bursts of status messages never pile up.
    Returns a :class:`SnackAperto` handle whose ``dismiss()`` hides it
    early. ``parent`` may be ``None`` for a plain window-bottom placement.
    """
    global _snack_corrente

    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.graphics import Color, Rectangle
    from kivy.metrics import dp, sp
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.label import Label

    from .material import hex_to_rgba, profile_for_window

    if _snack_corrente is not None:
        _snack_corrente.chiudi()

    profile = profile_for_window(Window)
    bordo = dp(SNACK_BORDO_DP)
    larghezza = larghezza_snackbar(Window.width, massimo=dp(SNACK_LARGHEZZA_MAX_DP),
                                   bordo=bordo)
    altezza = dp(SNACK_ALTEZZA_DP)
    zona = rect_da(parent) if parent is not None else Rect(0, 0, Window.width, Window.height)
    x, y = posizione_snackbar(zona, larghezza, altezza, Window.width, Window.height,
                              altezza_barra_inferiore(parent), bordo=bordo)

    stato = {"chiuso": False}

    def chiudi(*_):
        global _snack_corrente
        if stato["chiuso"]:
            return
        stato["chiuso"] = True
        evento.cancel()
        if overlay.parent is not None:
            overlay.parent.remove_widget(overlay)
        if _snack_corrente is not None and _snack_corrente.overlay is overlay:
            _snack_corrente = None

    pannello = FloatLayout(size_hint=(None, None), size=(larghezza, altezza), pos=(x, y))
    with pannello.canvas.before:
        Color(*hex_to_rgba(profile.tokens.colors["surface_container"], 0.97))
        fondo = Rectangle(pos=pannello.pos, size=pannello.size)
    pannello.bind(pos=lambda *_: setattr(fondo, "pos", pannello.pos),
                  size=lambda *_: setattr(fondo, "size", pannello.size))
    pannello.add_widget(Label(text=str(testo), markup=False, halign="center",
                              valign="middle", text_size=(larghezza - dp(24), altezza),
                              color=hex_to_rgba(profile.tokens.colors["text"]),
                              font_size=sp(profile.tokens.typography["label"])))

    # Pass-through overlay: the snack informs without ever eating touches.
    overlay = FloatLayout(size_hint=(1, 1))
    overlay.add_widget(pannello)
    evento = Clock.schedule_once(chiudi, max(float(durata), 0.0))
    Window.add_widget(overlay)
    _snack_corrente = SnackAperto(overlay=overlay, pannello=pannello, chiudi=chiudi)
    return _snack_corrente
