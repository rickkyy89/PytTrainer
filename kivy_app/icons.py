"""Glyph helpers: plain Kivy buttons render with Roboto, which lacks the
kebab (U+22EE) and check (U+2713) symbols, so icon buttons must use the
Material Design Icons font.  KivyMD 2.0 registers that font with Kivy's
LabelBase under the name ``Icons`` at app start, which is the only handle
that also resolves inside the Android python bundle; a raw path into the
kivymd package is the fallback and the plain symbol text the last resort.
"""

from __future__ import annotations

_NON_RISOLTO = object()
_risolta_cache: tuple[dict, str] | None | object = _NON_RISOLTO  # resolved once


def _risolvi() -> tuple[dict, str] | None:
    """``(md_icons, font_name_or_path)`` or None when the font is unusable."""
    try:
        import pathlib

        import kivymd
        from kivymd.icon_definitions import md_icons

        path = (pathlib.Path(kivymd.__file__).parent / "fonts"
                / "materialdesignicons-webfont.ttf")
        font = None
        try:
            from kivy.core.text import LabelBase

            if "Icons" in getattr(LabelBase, "_fonts", {}):
                font = "Icons"
        except Exception:
            font = None
        if font is None and path.is_file():
            font = str(path)
        return (md_icons, font) if font else None
    except Exception:
        return None


def glifo(nome: str, fallback: str) -> tuple[str, str | None]:
    """Return ``(text, font_name_or_path)`` for an MDI icon name."""
    global _risolta_cache
    if _risolta_cache is _NON_RISOLTO:
        _risolta_cache = _risolvi()
    risolta = _risolta_cache
    if risolta is not None:
        icone, font = risolta
        codepoint = icone.get(nome)
        if codepoint:
            return codepoint, font
    return fallback, None


def imposta_icona(widget, nome: str, fallback: str) -> None:
    """Set ``widget.text``/``widget.font_name`` to the MDI glyph of ``nome``."""
    testo, font = glifo(nome, fallback)
    widget.text = testo
    if font is not None:
        widget.font_name = font


# Unicode symbols used as button glyphs that Roboto lacks (tofu on Android).
# Each maps to the Material Design Icons glyph with the same meaning.
SIMBOLI = {
    "⋮": "dots-vertical",
    "‹": "chevron-left",
    "›": "chevron-right",
    "▸": "chevron-right",
    "▾": "menu-down",
    "✓": "check",
}


def da_simbolo(widget):
    """Swap a symbol-only ``widget.text`` for its MDI glyph; returns the widget."""
    nome = SIMBOLI.get(widget.text)
    if nome is not None:
        imposta_icona(widget, nome, widget.text)
    return widget
