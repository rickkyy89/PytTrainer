"""Headless tests for the MDI glyph helper used by symbol buttons."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from kivy_app.icons import SIMBOLI, da_simbolo, glifo, imposta_icona


class _Stub:
    def __init__(self, text=""):
        self.text = text
        self.font_name = ""


def test_glifo_conosciuto_usa_glyph_pua_e_font_reale():
    testo, font = glifo("dots-vertical", "⋮")
    assert testo != "⋮" and len(testo) == 1 and ord(testo) > 0xE000
    # LabelBase-registered name (KivyMD) or a real ttf path; both resolve.
    assert font == "Icons" or (font and Path(font).is_file())


def test_glifo_sconosciuto_cade_sul_fallback_senza_font():
    assert glifo("non-esiste-x", "?") == ("?", None)


def test_simboli_tutti_mappati_in_kivymd():
    for key, name in SIMBOLI.items():
        glyph, font = glifo(name, "?")
        assert font is not None, f"KivyMD non fornisce {name}"
        assert len(glyph) == 1 and ord(glyph) > 0xE000


def test_da_simbolo_sostituisce_solo_testi_glyph():
    kebab = da_simbolo(_Stub("⋮"))
    assert kebab.text != "⋮" and kebab.font_name
    testo = da_simbolo(_Stub("Salva"))
    assert testo.text == "Salva" and testo.font_name == ""


def test_imposta_icona_mantiene_fallback_senza_font():
    stub = _Stub()
    imposta_icona(stub, "non-esiste-x", "‹")
    assert stub.text == "‹" and stub.font_name == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
