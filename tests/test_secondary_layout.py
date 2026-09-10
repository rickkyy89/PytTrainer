from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.material import BUTTON_HEIGHTS, ViewportMetrics, adaptive_profile, pulsanti_correnti
from kivy_app.secondary_layout import secondary_layout

PRESET = BUTTON_HEIGHTS[pulsanti_correnti()]


def test_secondary_surfaces_have_scrollable_bounded_dialogs():
    layout = secondary_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"), "130"))
    assert layout.dialog_scrollable and layout.keyboard_aware
    assert layout.dialog_max_width > 0
    assert layout.minimum_target == PRESET


def test_secondary_targets_are_uniform_across_platforms():
    """Confirmed contract: the same button preset drives touch and pointer."""
    touch = secondary_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch")))
    pointer = secondary_layout(adaptive_profile(ViewportMetrics(1200, 800)))
    assert touch.minimum_target == pointer.minimum_target == PRESET
