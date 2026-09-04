from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.material import ViewportMetrics, adaptive_profile
from kivy_app.secondary_layout import secondary_layout


def test_secondary_surfaces_have_scrollable_bounded_dialogs():
    layout = secondary_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"), "130"))
    assert layout.dialog_scrollable and layout.keyboard_aware
    assert layout.dialog_max_width > 0
    assert layout.minimum_target == 48


def test_secondary_pointer_targets_remain_distinct_from_touch_targets():
    layout = secondary_layout(adaptive_profile(ViewportMetrics(1200, 800)))
    assert layout.minimum_target == 40
