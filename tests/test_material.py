"""Headless tests for the adaptive Material seam."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from kivy_app.material import ScalePreferenceStore, ViewportMetrics, adaptive_profile, primitive_specs


@pytest.mark.parametrize("width, category", [(400, "compact"), (599, "compact"), (600, "medium"), (959, "medium"), (960, "expanded")])
def test_profile_classifies_widths(width, category):
    assert adaptive_profile(ViewportMetrics(width, 800)).category == category


def test_profile_scales_system_and_explicit_choice():
    profile = adaptive_profile(ViewportMetrics(800, 600, system_density=2), "130")
    assert profile.scale == pytest.approx(2.6)
    assert profile.tokens.typography["body"] == pytest.approx(20.8)


def test_targets_and_reflow_differ_by_input_mode():
    touch = adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"))
    pointer = adaptive_profile(ViewportMetrics(1200, 800, input_mode="pointer"))
    assert touch.touch_target == 48
    assert pointer.touch_target == 40
    assert touch.layout("editor").columns == 1
    assert pointer.layout("editor").master_detail is True
    assert primitive_specs(touch)["button"]["min_height"] == 48


def test_scale_store_defaults_validates_and_writes_atomically(tmp_path):
    store = ScalePreferenceStore(tmp_path / "preferences.json")
    assert store.load_scale() == "auto"
    store.save_scale("115")
    assert store.load_scale() == "115"
    store.path.write_text(json.dumps({"scale": "invalid"}), encoding="utf-8")
    assert store.load_scale() == "auto"
    with pytest.raises(ValueError):
        store.save_scale("bad")
