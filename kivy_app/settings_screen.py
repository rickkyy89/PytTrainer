"""Dedicated, immediately-persisted Kivy settings view."""

from __future__ import annotations

from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput

from .material import profile_for_window
from .settings_layout import folder_rows


class SettingsScreen(BoxLayout):
    """Settings owns no draft: each callback persists before updating the UI."""

    def __init__(self, controller, preferences, *, on_back, on_text, on_buttons,
                 on_pen, on_destination, on_folder_change,
                 local_destination_available=True, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.controller = controller
        self.preferences = preferences
        self._on_back = on_back
        self._callbacks = (on_text, on_buttons, on_pen, on_destination)
        self._on_folder_change = on_folder_change
        self._local_destination_available = local_destination_available
        self._active_sliders = 0
        self._profile = profile_for_window(Window)
        self._build_header()
        self.scroll = ScrollView()
        self.body = BoxLayout(orientation="vertical", size_hint_y=None,
                              spacing=dp(12), padding=dp(12))
        self.body.bind(minimum_height=self.body.setter("height"))
        self.scroll.add_widget(self.body)
        self.add_widget(self.scroll)
        self._build_controls()

    def _build_header(self):
        bar = BoxLayout(size_hint_y=None, height=dp(self._profile.touch_target), spacing=dp(8))
        back = Button(text="‹", size_hint_x=None, width=dp(self._profile.touch_target))
        back.bind(on_release=lambda *_: self._on_back())
        bar.add_widget(back)
        bar.add_widget(Label(text="Impostazioni", halign="left"))
        self.add_widget(bar)

    def _section(self, text):
        label = Label(text=f"[b]{text}[/b]", markup=True, size_hint_y=None,
                      height=dp(self._profile.touch_target), halign="left")
        label.bind(width=lambda widget, value: setattr(widget, "text_size", (value, None)))
        self.body.add_widget(label)

    def _slider(self, title, minimum, maximum, value, callback, on_release=None):
        self._section(title)
        row = BoxLayout(size_hint_y=None, height=dp(self._profile.touch_target), spacing=dp(8))
        slider = Slider(min=minimum, max=maximum, value=value, step=1)
        shown = Label(text=str(int(value)), size_hint_x=None, width=dp(54))
        ready = {"value": False}

        def changed(_widget, new_value):
            shown.text = str(int(new_value))
            if ready["value"]:
                self._guard(lambda: callback(int(new_value)))

        slider.bind(value=changed)

        def touch_down(widget, touch):
            if widget.collide_point(*touch.pos):
                self._active_sliders += 1

        def touch_up(widget, touch):
            if self._active_sliders:
                self._active_sliders -= 1
            if on_release is not None and widget.collide_point(*touch.pos):
                on_release()

        slider.bind(on_touch_down=touch_down, on_touch_up=touch_up)
        row.add_widget(slider)
        row.add_widget(shown)
        self.body.add_widget(row)
        ready["value"] = True

    @property
    def slider_active(self):
        return self._active_sliders > 0

    def _build_controls(self):
        on_text, on_buttons, on_pen, on_destination = self._callbacks
        self._slider("Dimensione testo (pt)", 14, 32,
                     self.preferences.load_text(), on_text)

        self._section("Dimensione pulsanti")
        row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        current = self.preferences.load_button_preset()
        for value, label in (("compact", "Compatta · 44"),
                             ("standard", "Standard · 52"), ("large", "Grande · 60")):
            button = Button(text=("✓ " if value == current else "") + label)
            button.bind(on_release=lambda _, selected=value: self._guard(
                lambda: on_buttons(selected)))
            row.add_widget(button)
        self.body.add_widget(row)

        self._slider("Spessore penna", 2, 20, self.preferences.load_pen_width(), on_pen)

        self._section("Destinazione locale")
        if not self._local_destination_available:
            explanation = Label(
                text="Su PC la destinazione viene scelta nel dialogo Salva con nome.",
                size_hint_y=None, height=dp(self._profile.touch_target), halign="left")
            explanation.bind(width=lambda widget, value: setattr(
                widget, "text_size", (value, None)))
            self.body.add_widget(explanation)
            self._build_folders()
            return
        row = BoxLayout(size_hint_y=None, height=dp(self._profile.touch_target), spacing=dp(8))
        current_destination = self.controller.destinazione_locale
        for value, label in (("documenti", "Documenti/pyTrainer"),
                             ("download", "Download/pyTrainer")):
            button = Button(text=("✓ " if value == current_destination else "") + label)
            button.bind(on_release=lambda _, selected=value: self._guard(
                lambda: on_destination(selected)))
            row.add_widget(button)
        self.body.add_widget(row)
        self._build_folders()

    def _build_folders(self):
        self._section("Cartelle Drive")
        labels = self.controller.folder_labels()
        for model in folder_rows(labels, self.controller.folder_config.current_folder_id):
            row = BoxLayout(size_hint_y=None, height=dp(self._profile.touch_target), spacing=dp(6))
            select = Button(text=("✓ " if model.selected else "") + model.label,
                            halign="left", shorten=True)
            select.bind(on_release=lambda _, fid=model.folder_id: self._guard(
                lambda: self._folder_operation(lambda: self.controller.select_folder(fid))))
            row.add_widget(select)
            remove = Button(text="Rimuovi", size_hint_x=None, width=dp(92),
                            disabled=not model.removable)
            remove.bind(on_release=lambda _, fid=model.folder_id: self._confirm_remove(fid))
            row.add_widget(remove)
            self.body.add_widget(row)
        add_row = BoxLayout(size_hint_y=None, height=dp(self._profile.touch_target), spacing=dp(6))
        field = TextInput(hint_text="ID nuova cartella Drive", multiline=False)
        add = Button(text="Aggiungi", size_hint_x=None, width=dp(110))
        action = lambda *_: self._guard(lambda: self._folder_operation(
            lambda: self.controller.add_folder(field.text)))
        add.bind(on_release=action)
        field.bind(on_text_validate=action)
        add_row.add_widget(field)
        add_row.add_widget(add)
        self.body.add_widget(add_row)

    def _confirm_remove(self, folder_id):
        row = BoxLayout(spacing=dp(8), padding=dp(8))
        popup = Popup(title="Rimuovere questa cartella?", content=row,
                      size_hint=(0.82, None), height=dp(180))
        cancel = Button(text="Annulla")
        confirm = Button(text="Rimuovi")
        cancel.bind(on_release=lambda *_: popup.dismiss())
        confirm.bind(on_release=lambda *_: (popup.dismiss(), self._guard(
            lambda: self._folder_operation(lambda: self.controller.remove_folder(folder_id)))))
        row.add_widget(cancel)
        row.add_widget(confirm)
        popup.open()

    def _folder_operation(self, operation):
        operation()
        self._on_folder_change()

    def _guard(self, operation):
        try:
            operation()
        except Exception as exc:
            Popup(title="Errore", content=Label(text=str(exc)),
                  size_hint=(0.86, None), height=dp(190)).open()
