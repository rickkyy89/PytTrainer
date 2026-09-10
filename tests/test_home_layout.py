"""Headless presentation decisions for Home and read-only cards."""

from types import SimpleNamespace
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.home_layout import (HOME_MENU_LABELS, abbrevia_id, etichetta_recupero,
                                  home_toolbar_rows, readonly_card)
from kivy_app.material import ViewportMetrics, adaptive_profile


def test_readonly_cards_keep_long_content_and_reflow_frames():
    exercise = SimpleNamespace(
        name="Squat", repetitions="3x12", recovery="90 SEC",
        explanation="Spiegazione lunga che deve restare completa.", notes="Nota lunga.",
    )
    compact = readonly_card(exercise, adaptive_profile(ViewportMetrics(400, 800)))
    expanded = readonly_card(exercise, adaptive_profile(ViewportMetrics(1200, 800)))
    assert compact.explanation.endswith("completa.")
    assert compact.frame_axis == "vertical"
    assert expanded.frame_axis == "horizontal"


def test_expanded_profile_preserves_body_typography():
    profile = adaptive_profile(ViewportMetrics(1200, 800))
    assert profile.tokens.typography["body"] == 18
    assert profile.tokens.dimensions["content_max_width"] > 0


def test_readonly_recovery_label_is_explicit_and_empty_values_stay_empty():
    assert etichetta_recupero("90 SEC") == "Recupero: 90 SEC"
    assert etichetta_recupero("") == ""


def test_home_bottom_bar_has_same_minimal_actions_at_every_width():
    compact = adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"))
    expanded = adaptive_profile(ViewportMetrics(1200, 800))
    assert home_toolbar_rows(compact) == (("refresh", "create"),)
    assert home_toolbar_rows(expanded) == (("refresh", "create"),)
    assert HOME_MENU_LABELS == (
        "Scheda con AI", "Apri locale", "Apri cartella Drive", "Impostazioni")


def test_drive_id_is_abbreviated_but_short_ids_remain_readable():
    assert abbrevia_id("short-id") == "short-id"
    assert abbrevia_id("1234567890abcdefghijkl") == "123456…ghijkl"
