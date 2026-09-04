from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.material import ViewportMetrics, adaptive_profile
from kivy_app.workout_layout import workout_layout


def test_workout_compact_is_touch_first_and_stacks_frames():
    layout = workout_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"), "130"))
    assert layout.frame_axis == "vertical"
    assert layout.minimum_target == 48
    assert layout.body_font_size > 16
    assert layout.fixed_timer_bar


def test_workout_wide_keeps_large_typography_and_side_by_side_frames():
    layout = workout_layout(adaptive_profile(ViewportMetrics(1200, 800)))
    assert layout.frame_axis == "horizontal"
    assert layout.body_font_size == 16
    assert layout.minimum_target == 40
