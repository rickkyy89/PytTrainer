from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.editor_layout import editor_layout, field_columns
from kivy_app.material import ViewportMetrics, adaptive_profile


def test_editor_compact_policy_is_one_open_accordion_with_bottom_actions():
    policy = editor_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch")))
    assert policy.accordion and policy.labels_above
    assert policy.field_columns == 1
    assert policy.fixed_action_bar and policy.actions_in_overflow


def test_editor_wide_policy_uses_columns_but_keeps_actions_safe():
    policy = editor_layout(adaptive_profile(ViewportMetrics(1200, 800)))
    assert not policy.accordion and not policy.labels_above
    assert policy.field_columns == 4
    assert policy.fixed_action_bar


def test_field_columns_follow_width_and_respect_category_ceiling():
    medium = adaptive_profile(ViewportMetrics(700, 800, input_mode="touch"))
    expanded = adaptive_profile(ViewportMetrics(1200, 800))
    assert field_columns(medium, 1300) == 2
    assert field_columns(expanded, 1300) == 4
    assert field_columns(expanded, 950) == 3
    assert field_columns(expanded, 630) == 2
    assert field_columns(medium, 300) == 1
