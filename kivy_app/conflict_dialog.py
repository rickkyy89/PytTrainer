"""Conflict resolution dialog (ticket 10).

Shared by the home (open-time check) and the editor (save-time check):
presents both timestamps and the three allowed choices — keep local, keep
remote, duplicate — never a silent last-write-wins. Imported only from the
Kivy screens.
"""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup


SCELTE = (
    ("locale", "Tieni locale (sovrascrive Drive)"),
    ("remota", "Tieni remota (scarta modifiche locali)"),
    ("duplicata", "Duplica (nuova scheda su Drive)"),
)


def apri_dialogo_conflitto(controller, conflitto, on_esito):
    """Show the dialog and apply the chosen resolution.

    ``on_esito(choice, risultato_or_error)`` is called after
    ``controller.resolve_conflict``: ``risultato`` is the UploadResult /
    downloaded path for the successful choice, or the exception raised.
    """
    content = BoxLayout(orientation="vertical", spacing=8)
    testo = (
        f"Conflitto su {conflitto.name}\n"
        f"Versione locale modificata: {conflitto.local_modified_time}\n"
        f"Versione remota modificata: {conflitto.remote_modified_time}\n"
        f"(ultimo sync: {conflitto.last_sync_remote_modified_time})\n"
        "Cosa vuoi fare?"
    )
    content.add_widget(Label(text=testo, halign="left", valign="top",
                             size_hint_y=1.4, markup=False))
    for choice, etichetta in SCELTE:
        button = Button(text=etichetta, size_hint_y=None, height=52)

        def on_press(*_, choice=choice):
            popup.dismiss()
            try:
                risultato = controller.resolve_conflict(conflitto, choice=choice)
            except Exception as exc:
                on_esito(choice, exc)
            else:
                on_esito(choice, risultato)
        button.bind(on_release=on_press)
        content.add_widget(button)
    popup = Popup(title="Scheda modificata anche altrove", content=content,
                  size_hint=(0.92, 0.6))
    popup.open()
    return popup
