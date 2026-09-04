"""Headless geometry and deterministic-baseline tests."""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.material import ViewportMetrics, adaptive_profile
from kivy_app.responsive_harness import (
    DEFAULT_SCENARIOS, HarnessScenario, WidgetBox, render_baseline, run_scenario,
    validate_geometry,
)


def test_default_scenarios_cover_required_viewports_and_scales():
    names = {scenario.name for scenario in DEFAULT_SCENARIOS}
    assert {"phone-compact", "tablet-portrait", "tablet-landscape", "desktop-windows"} <= names
    assert all(scenario.scale in ("auto", "130") for scenario in DEFAULT_SCENARIOS)


def test_geometry_harness_separates_all_failure_types():
    profile = adaptive_profile(ViewportMetrics(400, 300, input_mode="touch"))
    boxes = [
        WidgetBox("outside", 390, 0, 20, 40), WidgetBox("zero", 0, 0, 0, 10),
        WidgetBox("small", 20, 20, 40, 40, interactive=True),
        WidgetBox("clipped", 100, 100, 40, 40, text_clipped=True),
        WidgetBox("overlap", 110, 110, 40, 40),
    ]
    kinds = {issue.kind for issue in validate_geometry(profile, boxes)}
    assert kinds == {"out-of-bounds", "zero-size", "target-too-small", "text-clipped", "overlap"}


def test_run_scenario_exercises_rotation_and_scale_without_window():
    scenario = HarnessScenario("tablet-landscape-130", ViewportMetrics(1024, 720, 2, "touch"), "130")

    def boxes(profile):
        assert profile.orientation == "landscape"
        assert profile.layout("editor").columns == 2
        return [WidgetBox("toolbar", 0, 0, 1024, profile.touch_target, interactive=True)]

    profile, _, issues = run_scenario(scenario, boxes)
    assert profile.scale == pytest.approx(2.6)
    assert issues == []


def test_baseline_is_deterministic_and_order_independent(tmp_path):
    scenario = HarnessScenario("phone", ViewportMetrics(400, 800))
    first = render_baseline(scenario, [WidgetBox("b", 2, 3, 4, 5), WidgetBox("a", 0, 1, 2, 3)])
    second = render_baseline(scenario, [WidgetBox("a", 0, 1, 2, 3), WidgetBox("b", 2, 3, 4, 5)])
    assert first == second
    baseline = Path(tmp_path) / "phone.svg"
    baseline.write_bytes(first)
    assert baseline.read_bytes() == second
