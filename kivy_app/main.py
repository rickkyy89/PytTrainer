"""Kivy UI entry point. Import this module only where Kivy is installed."""

from __future__ import annotations

from pathlib import Path
import sys

from core.platform import LocalCredentialsProvider

from .config import FolderConfigStore
from .controller import DriveHomeController, HomeUnavailableError


def build_controller(
    base_dir: str | Path | None = None, *, is_android: bool | None = None,
    android_bridge_factory=None,
) -> DriveHomeController:
    """Compose the platform credential provider only at application startup."""
    base = Path(base_dir or Path(__file__).resolve().parent.parent).expanduser()
    is_android = sys.platform == "android" if is_android is None else is_android

    if is_android:
        # Avoid importing pyjnius and Android-only code on the PC and in pytest.
        from .platform_android import AndroidCredentialProvider, PyjniusGoogleBridge
        bridge_factory = android_bridge_factory or PyjniusGoogleBridge
        credential_provider = AndroidCredentialProvider(bridge_factory())
        credential_provider.start_authorization()
    else:
        credential_provider = LocalCredentialsProvider(base)

    def drive_service_factory(credentials):
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=credentials)

    return DriveHomeController(
        FolderConfigStore(base / "drive-folders.json"), base / "drive-cache",
        credential_provider=credential_provider,
        drive_service_factory=drive_service_factory,
        base_dir=base,
    )


def build_pc_controller(base_dir: str | Path | None = None) -> DriveHomeController:
    """Compose the unchanged PC OAuth implementation."""
    return build_controller(base_dir, is_android=False)


def run() -> None:
    """Run the small PC Kivy shell without exposing Kivy to pytest imports."""
    from kivy.app import App
    from kivy.core.window import Window
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.image import Image
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.textinput import TextInput
    from kivy.utils import escape_markup

    from .editor_screen import EditorScreen
    from .export import DocExportController
    from .export_screen import ExportScreen
    from .media import MediaFlowController
    from .media_screen import MediaScreen
    from .workout import WorkoutSessionController
    from .workout_screen import WorkoutScreen

    controller = build_controller()
    if sys.platform == "android":
        from .platform_android import AndroidFrameExtractor
        media_backend = AndroidFrameExtractor()
    else:
        from core.platform import PcFfmpegBackend
        media_backend = PcFfmpegBackend()

    def _label_righe(testo, contenitore, *, font_size="16sp", **kw):
        label = Label(text=testo, markup=True, halign="left", valign="top",
                      size_hint_y=None, font_size=font_size, **kw)
        contenitore.bind(
            width=lambda _, v, l=label: setattr(l, "text_size", (max(v - 24, 10), None)))
        label.bind(texture_size=lambda l, ts: setattr(l, "height", ts[1]))
        return label

    def _area_scrollabile(spacing=8):
        scroll = ScrollView()
        contenuto = BoxLayout(orientation="vertical", size_hint_y=None, spacing=spacing)
        contenuto.bind(minimum_height=contenuto.setter("height"))
        scroll.add_widget(contenuto)
        return scroll, contenuto

    class PyTrainerApp(App):
        def build(self):
            self.title = "pyTrainer"
            self.stack = BoxLayout(orientation="vertical")
            self.home = BoxLayout(orientation="vertical", padding=12, spacing=8)
            toolbar = BoxLayout(size_hint_y=None, height=48, spacing=8)
            refresh = Button(text="Aggiorna", size_hint_x=None, width=140)
            refresh.bind(on_release=lambda *_: self.refresh())
            create = Button(text="Nuova scheda")
            create.bind(on_release=lambda *_: self.create_dialog())
            folders = Button(text="Cartelle", size_hint_x=None, width=140)
            folders.bind(on_release=lambda *_: self.folder_dialog())
            toolbar.add_widget(refresh)
            toolbar.add_widget(create)
            toolbar.add_widget(folders)
            self.home.add_widget(toolbar)
            self.status = Label(text="Premi Aggiorna per caricare le schede.",
                                size_hint_y=None, height=40, halign="left", valign="middle")
            self.status.bind(
                width=lambda _, v: setattr(self.status, "text_size", (v, None)))
            self.status.bind(
                texture_size=lambda l, ts: setattr(l, "height", max(ts[1], 40)))
            self.home.add_widget(self.status)
            self.home_body = BoxLayout(orientation="vertical", spacing=8)
            self.home.add_widget(self.home_body)
            self.stack.add_widget(self.home)
            self._ultime_schede = []
            self._editor_view = None
            Window.bind(on_request_close=self._on_request_close)
            self.show_home()
            return self.stack

        def show_home(self):
            self._editor_view = None
            self.stack.clear_widgets()
            self.stack.add_widget(self.home)
            self._render_lista()

        def go_home_message(self, message):
            self.show_home()
            self.refresh()
            self.status.text = message

        def edit(self, remote):
            try:
                editor = controller.open_for_edit(remote)
            except HomeUnavailableError as exc:
                self.status.text = str(exc)
                return
            self.show_editor(remote, editor)

        def show_editor(self, remote, editor):
            self.stack.clear_widgets()
            self._editor_view = EditorScreen(
                controller, editor, remote,
                on_back=lambda: self._torna_in_lettura(remote),
                open_media=lambda ed, i: self.open_media(remote, ed, i),
                on_export=lambda ed: self.open_export(remote, ed),
                on_conflict_exit=self.go_home_message,
            )
            self.stack.add_widget(self._editor_view)

        def _on_request_close(self, *_):
            if self._editor_view is None:
                return False
            if self._editor_view.modifiche_non_salvate:
                self._editor_view.richiedi_uscita()
                return True
            return False

        def _torna_in_lettura(self, remote):
            self.show_home()
            self._apri_in_lettura(remote)

        def open_export(self, remote, editor):
            try:
                export = DocExportController(
                    editor, credential_provider=controller.credential_provider,
                    base_dir=controller.base_dir,
                )
            except Exception as exc:
                self.status.text = str(exc)
                return
            self.stack.clear_widgets()
            self.stack.add_widget(ExportScreen(export, on_back=lambda: self.show_editor(remote, editor)))

        def open_media(self, remote, editor, indice):
            try:
                output_dir = editor.output_frames()
                media = MediaFlowController(
                    editor.esercizi[indice], output_dir,
                    backend=media_backend,
                    transaction=lambda operation: editor.transazione_media(
                        operation, output_dir=output_dir),
                )
            except Exception as exc:  # EditorValidationError e simili
                self.status.text = str(exc)
                return
            self.stack.clear_widgets()
            self.stack.add_widget(MediaScreen(media, on_back=lambda: self.show_editor(remote, editor)))

        def refresh(self):
            try:
                records = controller.refresh()
            except HomeUnavailableError as exc:
                self.status.text = str(exc)
                return
            self._ultime_schede = records
            self.status.text = f"{len(records)} schede nella cartella corrente."
            self._render_lista()

        def _render_lista(self):
            self.home_body.clear_widgets()
            scroll, contenuto = _area_scrollabile()
            self.home_body.add_widget(scroll)
            for remote in self._ultime_schede:
                row = BoxLayout(size_hint_y=None, height=56, spacing=6)
                open_button = Button(text=f"{remote.name}   —   {remote.modified_time}")
                open_button.bind(on_release=lambda _, item=remote: self.open(item))
                delete = Button(text="Elimina", size_hint_x=None, width=100)
                delete.bind(on_release=lambda _, item=remote: self.confirm_delete(item))
                row.add_widget(open_button)
                row.add_widget(delete)
                contenuto.add_widget(row)

        def open(self, remote):
            try:
                conflitto = controller.check_conflict(remote)
            except HomeUnavailableError as exc:
                self.status.text = str(exc)
                return
            if conflitto is not None:
                def esito(choice, risultato):
                    if isinstance(risultato, Exception):
                        self.status.text = str(risultato)
                        return
                    self.status.text = {
                        "locale": "Conflitto risolto con la versione locale.",
                        "remota": "Conflitto risolto con la versione remota.",
                        "duplicata": "Versione locale duplicata su Drive.",
                    }[choice]
                    self._apri_in_lettura(remote)
                from .conflict_dialog import apri_dialogo_conflitto
                apri_dialogo_conflitto(controller, conflitto, esito,
                                       local_path=controller.cache_path(remote.name))
                return
            self._apri_in_lettura(remote)

        def _apri_in_lettura(self, remote):
            try:
                scheda = controller.open(remote)
            except HomeUnavailableError as exc:
                self.status.text = str(exc)
                return
            self.status.text = f"{scheda.name}: sola lettura"
            self.home_body.clear_widgets()
            bar = BoxLayout(size_hint_y=None, height=48, spacing=8)
            back = Button(text="< Lista", size_hint_x=None, width=120)
            back.bind(on_release=lambda *_: self.refresh())
            edit = Button(text="Modifica")
            edit.bind(on_release=lambda *_: self.edit(remote))
            workout = Button(text="Allenati")
            workout.bind(on_release=lambda *_: self.open_workout(remote))
            bar.add_widget(back)
            bar.add_widget(edit)
            bar.add_widget(workout)
            scroll, contenuto = _area_scrollabile(spacing=12)
            gruppo_corrente = object()
            for exercise in scheda.exercises:
                gruppo = (exercise.group or "").strip()
                if gruppo != gruppo_corrente:
                    gruppo_corrente = gruppo
                    if gruppo:
                        contenuto.add_widget(_label_righe(
                            f"[b][color=62c0a2][size=19]"
                            f"{escape_markup(gruppo.upper())}[/size][/color][/b]", contenuto))
                contenuto.add_widget(self._card_lettura(exercise))
            self.home_body.add_widget(bar)
            self.home_body.add_widget(scroll)

        def _card_lettura(self, exercise):
            card = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4, padding=6)
            card.bind(minimum_height=card.setter("height"))
            titolo = f"[b][size=20]{escape_markup(exercise.name or '(senza nome)')}[/size][/b]"
            if exercise.repetitions:
                titolo += f"   [size=17]{escape_markup(exercise.repetitions)}[/size]"
            if exercise.recovery:
                titolo += (f"   [size=17][color=62c0a2]"
                           f"{escape_markup(exercise.recovery)}[/color][/size]")
            card.add_widget(_label_righe(titolo, card))
            if (exercise.explanation or "").strip():
                card.add_widget(_label_righe(
                    f"[color=b3b3b3][size=15]{escape_markup(exercise.explanation)}"
                    "[/size][/color]", card))
            if (exercise.notes or "").strip():
                card.add_widget(_label_righe(
                    f"[i][color=b3b3b3][size=15]Note: {escape_markup(exercise.notes)}"
                    "[/size][/color][/i]", card))
            frames = BoxLayout(size_hint_y=None, height=260, spacing=6)
            for percorso in (exercise.frame_start, exercise.frame_finish):
                if percorso:
                    frames.add_widget(Image(source=percorso, fit_mode="contain"))
                else:
                    vuoto = BoxLayout()
                    vuoto.add_widget(Label(text="frame non estratto",
                                           font_size="14sp", color=(0.5, 0.5, 0.5, 1)))
                    frames.add_widget(vuoto)
            card.add_widget(frames)
            return card

        def open_workout(self, remote):
            try:
                esercizi = controller.open_for_workout(remote)
            except HomeUnavailableError as exc:
                self.status.text = str(exc)
                return
            session = WorkoutSessionController(esercizi)
            self.stack.clear_widgets()
            self.stack.add_widget(WorkoutScreen(session,
                                                on_back=lambda: self._torna_in_lettura(remote)))

        def create_dialog(self):
            input_name = TextInput(hint_text="Nome scheda")
            popup = Popup(title="Nuova scheda", content=input_name, size_hint=(0.8, 0.3))
            input_name.bind(on_text_validate=lambda *_: (popup.dismiss(), self.create(input_name.text)))
            popup.open()

        def create(self, name):
            try:
                controller.create(name)
                self.refresh()
            except HomeUnavailableError as exc:
                self.status.text = str(exc)

        def confirm_delete(self, remote):
            buttons = BoxLayout(spacing=8)
            popup = Popup(title=f"Eliminare {remote.name}?", content=buttons, size_hint=(0.8, 0.25))
            cancel = Button(text="Annulla")
            confirm = Button(text="Elimina")
            cancel.bind(on_release=lambda *_: popup.dismiss())
            confirm.bind(on_release=lambda *_: self.delete(remote, popup))
            buttons.add_widget(cancel)
            buttons.add_widget(confirm)
            popup.open()

        def delete(self, remote, popup):
            popup.dismiss()
            try:
                controller.delete(remote)
                self.refresh()
            except HomeUnavailableError as exc:
                self.status.text = str(exc)

        def folder_dialog(self):
            content = BoxLayout(orientation="vertical", spacing=6)
            for folder_id in controller.folder_config.folder_ids:
                folder = Button(text=folder_id)
                folder.bind(on_release=lambda _, value=folder_id: self.select_folder(value, popup))
                content.add_widget(folder)
            input_id = TextInput(hint_text="Nuovo ID cartella Drive", multiline=False)
            content.add_widget(input_id)
            popup = Popup(title="Cartelle Drive", content=content, size_hint=(0.8, 0.55))
            input_id.bind(on_text_validate=lambda *_: self.add_folder(input_id.text, popup))
            popup.open()

        def select_folder(self, folder_id, popup):
            try:
                controller.select_folder(folder_id)
                popup.dismiss()
                self.refresh()
            except (HomeUnavailableError, ValueError) as exc:
                self.status.text = str(exc)

        def add_folder(self, folder_id, popup):
            try:
                controller.add_folder(folder_id)
                popup.dismiss()
                self.refresh()
            except (HomeUnavailableError, ValueError) as exc:
                self.status.text = str(exc)

    PyTrainerApp().run()


if __name__ == "__main__":
    run()
