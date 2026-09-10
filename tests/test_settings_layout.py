"""Headless tests for settings persistence and folder presentation."""

import json

from kivy_app.material import ScalePreferenceStore
from kivy_app.settings_layout import folder_rows, settings_return_action


def test_old_scale_and_auto_text_are_migrated_to_confirmed_defaults(tmp_path):
    path = tmp_path / "ui-preferences.json"
    store = ScalePreferenceStore(path)
    cases = {"100": "compact", "auto": "standard", "115": "standard", "130": "large"}
    for old, expected in cases.items():
        path.write_text(json.dumps({"scale": old, "text": "auto"}), encoding="utf-8")
        assert store.load_button_preset() == expected
        assert store.load_text() == 18
        store.migrate_legacy()
        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert persisted == {"text": 18, "button_preset": expected}


def test_settings_values_persist_immediately_and_are_bounded(tmp_path):
    store = ScalePreferenceStore(tmp_path / "ui-preferences.json")
    assert store.load_button_preset() == "standard"
    assert store.load_text() == 18
    assert store.load_pen_width() == 6
    store.save_button_preset("large")
    store.save_text(32)
    store.save_pen_width(20)
    assert (store.load_button_preset(), store.load_text(), store.load_pen_width()) == (
        "large", 32, 20)


def test_folder_rows_show_name_abbreviated_id_selection_and_last_guard():
    rows = folder_rows((("1234567890abcdef", "Palestra"), ("two", "Clienti")), "two")
    assert rows[0].label == "Palestra  ·  123456…abcdef"
    assert rows[1].selected is True
    assert all(row.removable for row in rows)
    assert folder_rows((("only", "Solo"),), "only")[0].removable is False


def test_settings_return_restyles_retained_state_and_rebuilds_only_safe_views():
    assert settings_return_action("editor", False) == "retain"
    assert settings_return_action("editor", True) == "restyle-retained"
    assert settings_return_action("home", True) == "rebuild-preserving-scroll"
    assert settings_return_action("readonly", True) == "rebuild-preserving-scroll"
