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
    etichetta_testo, imposta_scala, imposta_testo, input_mode_for_platform,
    markup_px, primitive_specs, profile_for_window, scala_corrente,
    testo_corrente as _testo_corrente,
)


@pytest.mark.parametrize("width, category", [(400, "compact"), (599, "compact"), (600, "medium"), (959, "medium"), (960, "expanded")])
def test_profile_classifies_widths(width, category):
    assert adaptive_profile(ViewportMetrics(width, 800)).category == category


def test_profile_scales_system_and_explicit_choice():
    profile = adaptive_profile(ViewportMetrics(800, 600, system_density=2), "130")
    assert profile.scale == pytest.approx(2.6)
    assert profile.tokens.typography["body"] == 19
    assert profile.tokens.spacing["md"] == pytest.approx(15.6)


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
    assert store.load_text() == "auto"  # old scale-only files remain valid
    store.save_text(24)
    assert store.load_scale() == "115"
    assert store.load_text() == 24
    store.path.write_text(json.dumps({"scale": "invalid"}), encoding="utf-8")
    assert store.load_scale() == "auto"
    with pytest.raises(ValueError):
        store.save_scale("bad")


def test_text_preference_is_separate_bounded_and_global(tmp_path):
    store = ScalePreferenceStore(tmp_path / "preferences.json")
    store.save_text(imposta_testo(22))
    assert _testo_corrente() == 22
    assert etichetta_testo() == "Testo 22 pt"
    assert adaptive_profile(ViewportMetrics(400, 800), "130").tokens.typography["body"] == 22
    with pytest.raises(ValueError):
        imposta_testo(33)
    imposta_testo("auto")
    assert etichetta_testo() == "Testo auto"


def test_auto_text_adapts_and_touch_never_drops_below_20sp():
    phone = adaptive_profile(ViewportMetrics(400, 800, 3, "touch"), text="auto")
    tablet = adaptive_profile(ViewportMetrics(800, 1200, 2, "touch"), text="auto")
    desktop = adaptive_profile(ViewportMetrics(1200, 800, 1, "pointer"), text="auto")
    assert phone.tokens.typography["body"] == 21
    assert tablet.tokens.typography["body"] >= 20
    assert desktop.tokens.typography["body"] == 18


def test_markup_size_converts_sp_to_pixels_and_keeps_reading_correction():
    profile = adaptive_profile(ViewportMetrics(400, 800, 2.5, "touch"), text=21)
    assert markup_px(profile, profile.tokens.typography["body"], correction=1.2) == 63


def test_semantic_palette_has_teal_coral_containers_and_error_roles():
    colors = adaptive_profile(ViewportMetrics(400, 800), text=20).tokens.colors
    assert colors["primary"] == colors["accent"]
    assert colors["coral"].startswith("#")
    assert {"primary_container", "surface_container", "error_container", "on_error"} <= colors.keys()


def test_input_mode_is_touched_only_on_android_platforms():
    assert input_mode_for_platform("android") == "touch"
    assert input_mode_for_platform("win32") == "pointer"
    assert input_mode_for_platform("linux") == "pointer"


def test_hex_to_rgba_normalises_material_token_colors():
    red = hex_to_rgba("#FF0000")
    assert red == pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert hex_to_rgba("#00FF00", 0.5) == pytest.approx((0.0, 1.0, 0.0, 0.5))


def test_profile_for_window_divides_px_by_injected_factor_without_real_window():
    fake = SimpleNamespace(width=1920, height=1200, density=1.0)
    profile = profile_for_window(fake, input_mode="pointer", px_per_dp=2.0)
    assert profile.viewport.width_dp == 960
    assert profile.category == "expanded"
    assert profile.scale == 2.0


def test_profile_for_window_falls_back_to_window_density_headless():
    fake = SimpleNamespace(width=1600, height=2560, density=2.0)
    import kivy_app.material as material
    original = material._px_per_dp
    try:
        material._px_per_dp = lambda window: getattr(window, "density", 1.0)
        profile = profile_for_window(fake, input_mode="touch")
        assert profile.viewport.width_dp == 800
        assert profile.category == "medium"
        assert profile.layout("home").master_detail is False
    finally:
        material._px_per_dp = original


def test_profile_for_window_defaults_input_mode_from_platform(monkeypatch):
    import kivy_app.material as material
    monkeypatch.setattr(material, "input_mode_for_platform", lambda platform=None: "touch")
    fake = SimpleNamespace(width=800, height=1200, density=1.0)
    profile = profile_for_window(fake, px_per_dp=1.0)
    assert profile.touch_target == 48


def test_imposta_scala_alimenta_profile_for_window_senza_riavvio(tmp_path, monkeypatch):
    import kivy_app.material as material
    store = ScalePreferenceStore(tmp_path / "prefs.json")
    monkeypatch.setattr(material, "scala_corrente", lambda: "auto")
    fake = SimpleNamespace(width=800, height=600, density=2.0)
    assert profile_for_window(fake, px_per_dp=2.0).scale == 2.0
    monkeypatch.setattr(material, "scala_corrente", lambda: "130")
    assert profile_for_window(fake, px_per_dp=2.0).scale == pytest.approx(2.6)
    assert store.load_scale() == "auto"
    store.save_scale(imposta_scala("115"))
    assert store.load_scale() == "115"
    assert scala_corrente() == "115"
    with pytest.raises(ValueError):
        imposta_scala("200")
    imposta_scala("auto")
