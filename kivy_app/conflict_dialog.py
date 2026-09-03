"""Conflict resolution dialog (ticket 10).

Shared by the home (open-time check) and the editor (save-time check):
presents both timestamps and the three allowed choices — keep local, keep
remote, duplicate — never a silent last-write-wins. Imported only from the
Kivy screens.
"""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup


SCELTE = (
    ("locale", "Tieni locale (sovrascrive Drive)"),
    ("remota", "Tieni remota (scarta modifiche locali)"),
    ("duplicata", "Duplica (nuova scheda su Drive)"),
)


def apri_dialogo_conflitto(controller, conflitto, on_esito, *, local_path=None):
    """Show the dialog and apply the chosen resolution.

    Resolution runs on a worker thread (network I/O must not freeze the UI or
    ANR Android); every button is disabled while it runs so a second choice
    cannot start a concurrent operation. ``on_esito(choice, risultato)`` fires
    on the main thread, with the exception as ``risultato`` on failure.
    """
    content = BoxLayout(orientation="vertical", spacing=8)
    testo = (
        f"Conflitto su {conflitto.name}\n"
        f"Versione locale modificata: {conflitto.local_modified_time}\n"
        f"Versione remota modificata: {conflitto.remote_modified_time}\n"
        f"(ultimo sync: {conflitto.last_sync_remote_modified_time})\n"
        "Cosa vuoi fare?"
    )
    label = Label(text=testo, halign="left", valign="top", markup=False)
    label.bind(texture_size=label.setter("size"))
    content.add_widget(label)
    buttons: list[Button] = []
    state = {"busy": False}

    def on_press(choice):
        if state["busy"]:
            return
        state["busy"] = True
        for other in buttons:
            other.disabled = True
        status_label.text = "Attendi, risolvere il conflitto…"

        def worker():
            try:
                risultato = controller.resolve_conflict(conflitto, choice=choice,
                                                        local_path=local_path)
            except Exception as exc:  # surfaced to on_esito as the result
                Clock.schedule_once(lambda _, exc=exc: finish(exc), 0)
            else:
                Clock.schedule_once(lambda _, risultato=risultato: finish(risultato), 0)

        def finish(risultato):
            popup.dismiss()
            on_esito(choice, risultato)

        threading.Thread(target=worker, daemon=True).start()

    status_label = Label(text="", size_hint_y=None, height=24, markup=False)
    for choice, etichetta in SCELTE:
        button = Button(text=etichetta, size_hint_y=None, height=52)
        button.bind(on_release=lambda _, choice=choice: on_press(choice))
        buttons.append(button)
        content.add_widget(button)
    content.add_widget(status_label)
    popup = Popup(title="Scheda modificata anche altrove", content=content,
                  size_hint=(0.92, 0.65))
    popup.open()
    return popup
