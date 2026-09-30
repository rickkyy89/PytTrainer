"""Regression tests for Kivy-specific editor interactions."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("kivy")

from kivy.core.window import Window
from kivy.uix.behaviors.focus import FocusBehavior

from kivy_app.editor import SchedaEditorController
from kivy_app.editor_screen import EditorScreen


def _editor_screen():
    esercizio = {
        "nome": "Squat",
        "gruppo": "Gambe",
        "ripetizioni": "3x12",
        "recupero": "90 SEC",
        "spiegazione": "Scendi.",
        "note": "",
        "video_url": "",
        "ts_start": None,
        "ts_finish": None,
        "frame_start": None,
        "frame_finish": None,
    }
    editor = SchedaEditorController([esercizio], percorso_bundle="scheda.scheda")
    return editor, EditorScreen(
        SimpleNamespace(avvertenza=None), editor, None, on_back=lambda: None
    )


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_editor_fields_request_a_real_android_text_input_connection():
    _editor, screen = _editor_screen()

    try:
        assert screen._fields
        assert {field.input_type for field in screen._fields} == {"text"}
    finally:
        screen.dispose()


@pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")
def test_switching_between_real_text_inputs_commits_without_reentrant_keyboard_release():
    editor, screen = _editor_screen()
    first, second = screen._fields[:2]
    android_keyboard_release = None

    try:
        first.focus = True
        first.text = "Squat profondo"
        keyboard = first._keyboard

        def android_keyboard_release(_instance, focused):
            if not focused:
                del FocusBehavior._keyboards[keyboard]

        # Android's SDL keyboard can already be absent from Kivy's registry
        # when a reentrant focus=False reaches TextInput._unbind_keyboard.
        # Desktop SDL has different teardown timing, so emulate only that
        # platform state while retaining real TextInput widgets and focus flow.
        second.bind(focus=android_keyboard_release)

        # This is the Android crash path: Kivy removes focus from ``first``
        # while assigning its keyboard to ``second``.  The blur callback must
        # not change focus again during that transfer.
        second.focus = True

        assert editor.esercizi[0]["nome"] == "Squat profondo"
        assert second.focus is True
    finally:
        if android_keyboard_release is not None:
            second.unbind(focus=android_keyboard_release)
        first.focus = False
        second.focus = False
        screen.dispose()
