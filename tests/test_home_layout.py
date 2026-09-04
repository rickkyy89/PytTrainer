"""Headless presentation decisions for Home and read-only cards."""

from types import SimpleNamespace
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.home_layout import readonly_card
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
    assert profile.tokens.typography["body"] == 16
    assert profile.tokens.dimensions["content_max_width"] > 0
