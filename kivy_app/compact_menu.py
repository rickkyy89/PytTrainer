"""Compact global actions menu used by secondary Kivy screens."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.popup import Popup


def apri_menu(actions):
    """Open a small touch-friendly popup for global actions.

    ``actions`` is an iterable of ``(label, callback)`` pairs. The popup is
    dismissed before invoking the callback so actions that rebuild the root
    screen cannot leave an orphaned overlay behind.
    """
    content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    popup = Popup(title="Menu", content=content, size_hint=(0.72, None),
                  height=dp(56 + 56 * len(actions)), auto_dismiss=True)
    for label, callback in actions:
        button = Button(text=label, size_hint_y=None, height=dp(48))
        button.bind(on_release=lambda *_args, cb=callback: (popup.dismiss(), cb()))
        content.add_widget(button)
    popup.open()
    return popup
