"""Headless tests for the adaptive Material seam."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from types import SimpleNamespace

from kivy_app.material import (
    ScalePreferenceStore, ViewportMetrics, adaptive_profile, hex_to_rgba,
    imposta_scala, input_mode_for_platform, primitive_specs, profile_for_window,
    scala_corrente,
)


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


def test_input_mode_is_touched_only_on_android_platforms():
    assert input_mode_for_platform("android") == "touch"
    assert input_mode_for_platform("win32") == "pointer"
    assert input_mode_for_platform("linux") == "pointer"


def test_hex_to_rgba_normalises_material_token_colors():
    red = hex_to_rgba("#FF0000")
    assert red == pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert hex_to_rgba("#00FF00", 0.5) == pytest.approx((0.0, 1.0, 0.0, 0.5))


def test_profile_for_window_divides_by_injected_density_without_real_window():
    fake = SimpleNamespace(width=1920, height=1200, density=2.0)
    profile = profile_for_window(fake, input_mode="pointer")
    assert profile.viewport.width_dp == 960
    assert profile.category == "expanded"
    assert profile.scale == 2.0


def test_profile_for_window_defaults_input_mode_from_platform(monkeypatch):
    import kivy_app.material as material
    monkeypatch.setattr(material, "input_mode_for_platform", lambda platform=None: "touch")
    fake = SimpleNamespace(width=800, height=1200, density=1.0)
    profile = profile_for_window(fake)
    assert profile.touch_target == 48


def test_imposta_scala_alimenta_profile_for_window_senza_riavvio(tmp_path, monkeypatch):
    import kivy_app.material as material
    store = ScalePreferenceStore(tmp_path / "prefs.json")
    monkeypatch.setattr(material, "scala_corrente", lambda: "auto")
    fake = SimpleNamespace(width=800, height=600, density=2.0)
    assert profile_for_window(fake).scale == 2.0
    monkeypatch.setattr(material, "scala_corrente", lambda: "130")
    assert profile_for_window(fake).scale == pytest.approx(2.6)
    assert store.load_scale() == "auto"
    store.save_scale(imposta_scala("115"))
    assert store.load_scale() == "115"
    assert scala_corrente() == "115"
    with pytest.raises(ValueError):
        imposta_scala("200")
    imposta_scala("auto")
