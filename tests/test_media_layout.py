from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.material import ViewportMetrics, adaptive_profile
from kivy_app.media_layout import media_layout


def test_media_stacks_frames_and_keeps_touch_targets_on_compact():
    layout = media_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch")))
    assert layout.vertical_page and layout.frame_axis == "vertical"
    assert layout.target_minimum == 48
    assert layout.keyboard_inset_aware


def test_media_uses_horizontal_frames_on_wide_pointer_view():
    layout = media_layout(adaptive_profile(ViewportMetrics(1200, 800)))
    assert layout.frame_axis == "horizontal"
    assert layout.target_minimum == 40
