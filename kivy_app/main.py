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
    from kivy.core.window import Window
    from kivy.metrics import dp, sp
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.image import Image
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.textinput import TextInput
    from kivy.utils import escape_markup
    from kivymd.app import MDApp
    from kivymd.uix.card import MDCard

    from .editor_screen import EditorScreen
    from .export import DocExportController
    from .export_screen import ExportScreen
    from .media import MediaFlowController
    from .media_screen import MediaScreen
    from .workout import WorkoutSessionController
    from .workout_screen import WorkoutScreen
    from .home_layout import home_toolbar_rows, readonly_card
    from .material import (TEXT_SIZE_MAX, TEXT_SIZE_MIN, TEXT_SIZE_STEP, ScalePreferenceStore,
                           etichetta_testo, hex_to_rgba, imposta_scala,
                           imposta_testo, markup_px, profile_for_window,
                           scala_corrente, testo_corrente)
    from .theme import applica_tema, aggiorna_testo_widget, configura_tema_md
    from .compact_menu import apri_menu
    from .version import version_label

    controller = build_controller()
    scala_store = ScalePreferenceStore(controller.base_dir / "ui-preferences.json")
    imposta_scala(scala_store.load_scale())
    imposta_testo(scala_store.load_text())
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

    def _ui_profile():
        return profile_for_window(Window)

    class PyTrainerApp(MDApp):
        def build(self):
            self.title = "pyTrainer"
            self.stack = BoxLayout(orientation="vertical")
            self._ultime_schede = []
            self._editor_view = None
            self._view_kind = "home"
            self._readonly_remote = None
            self._readonly_scheda = None
            self._costruisce_home()
            Window.bind(on_request_close=self._on_request_close)
            self.show_home()
            return self.stack

        def _costruisce_home(self):
            profile = _ui_profile()
            applica_tema(profile)
            configura_tema_md(self.theme_cls, profile)
            tokens = profile.tokens
            self.home = BoxLayout(orientation="vertical",
                                  padding=dp(tokens.spacing["md"]),
                                  spacing=dp(tokens.spacing["sm"]))
            toolbar_rows = home_toolbar_rows(profile)
            toolbar = BoxLayout(orientation="vertical" if len(toolbar_rows) > 1 else "horizontal",
                                size_hint_y=None,
                                height=dp(tokens.dimensions["toolbar_height"] *
                                          len(toolbar_rows) +
                                          (tokens.spacing["xs"] if len(toolbar_rows) > 1 else 0)),
                                spacing=dp(tokens.spacing["xs"]))
            first_row = BoxLayout(spacing=dp(tokens.spacing["xs"]))
            second_row = (BoxLayout(spacing=dp(tokens.spacing["xs"]))
                          if profile.category == "compact" else first_row)
            refresh = Button(text="Aggiorna")
            refresh.bind(on_release=lambda *_: self.refresh())
            create = Button(text="Nuova scheda")
            create.background_color = hex_to_rgba(tokens.colors["coral"])
            create.color = hex_to_rgba(tokens.colors["on_coral"])
            create.bind(on_release=lambda *_: self.create_dialog())
            folders = Button(text="Cartelle")
            folders.bind(on_release=lambda *_: self.folder_dialog())
            self._scala_btn = Button(text=f"Scala {scala_corrente()}")
            self._scala_btn.bind(on_release=lambda *_: self.ciclo_scala())
            self._testo_btn = Button(text=etichetta_testo())
            self._testo_btn.bind(on_release=lambda *_: self.apri_testo())
            for widget in (refresh, create, folders):
                first_row.add_widget(widget)
            for widget in (self._scala_btn, self._testo_btn):
                second_row.add_widget(widget)
            toolbar.add_widget(first_row)
            if second_row is not first_row:
                toolbar.add_widget(second_row)
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
            footer = Label(text=version_label(), size_hint_y=None,
                           height=dp(max(tokens.typography["caption"] + 6, 22)),
                            font_size=sp(tokens.typography["caption"]),
                           color=hex_to_rgba(tokens.colors["muted"]), halign="right")
            footer.bind(width=lambda _, value: setattr(footer, "text_size", (value, None)))
            self.home.add_widget(footer)

        def ciclo_scala(self):
            ordine = ["auto", "100", "115", "130"]
            nuova = ordine[(ordine.index(scala_corrente()) + 1) % len(ordine)]
            imposta_scala(nuova)
            scala_store.save_scale(nuova)
            self._dispose_current_view()
            self._costruisce_home()
            self.show_home()
            self.status.text = f"Scala: {nuova}."

        def show_home(self):
            self._editor_view = None
            self._view_kind = "home"
            self._readonly_remote = None
            self._readonly_scheda = None
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
            self._view_kind = "editor"
            self._editor_view = EditorScreen(
                controller, editor, remote,
                on_back=lambda: self._torna_in_lettura(remote),
                open_media=lambda ed, i: self.open_media(remote, ed, i),
                on_export=lambda ed: self.open_export(remote, ed),
                on_conflict_exit=self.go_home_message,
                on_menu=self.apri_menu,
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
            self._view_kind = "export"
            self.stack.add_widget(ExportScreen(export, on_back=lambda: self.show_editor(remote, editor),
                                               on_menu=self.apri_menu))

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
            self._view_kind = "media"
            self.stack.add_widget(MediaScreen(media, on_back=lambda: self.show_editor(remote, editor),
                                              on_menu=self.apri_menu))

        def apri_menu(self):
            return apri_menu((
                ("Aggiorna", self._lista_aggiornata),
                ("Nuova scheda", lambda: self._azione_da_home(self.create_dialog)),
                ("Cartelle", lambda: self._azione_da_home(self.folder_dialog)),
                (f"Scala {scala_corrente()}", self.ciclo_scala),
                (etichetta_testo(), self.apri_testo),
            ))

        def _azione_da_home(self, action):
            if self._view_kind != "home":
                self._dispose_current_view()
                self.show_home()
            action()

        def _dispose_current_view(self):
            current = self.stack.children[0] if self.stack.children else None
            if current is not None and hasattr(current, "dispose"):
                current.dispose()

        def apri_testo(self):
            profile = _ui_profile()
            content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
            value = Label(text=etichetta_testo(), size_hint_y=None,
                          height=dp(profile.touch_target))
            controls = BoxLayout(size_hint_y=None, height=dp(profile.touch_target),
                                 spacing=dp(8))
            popup = Popup(title="Dimensione testo", content=content,
                          size_hint=(0.82, None), height=dp(225))

            def cambia(nuovo):
                imposta_testo(nuovo)
                scala_store.save_text(nuovo)
                value.text = etichetta_testo()
                self._applica_testo_corrente()

            auto = Button(text="Auto")
            meno = Button(text="−")
            piu = Button(text="+")
            auto.bind(on_release=lambda *_: cambia("auto"))
            meno.bind(on_release=lambda *_: cambia(
                max(TEXT_SIZE_MIN, self._testo_numerico() - TEXT_SIZE_STEP)))
            piu.bind(on_release=lambda *_: cambia(
                min(TEXT_SIZE_MAX, self._testo_numerico() + TEXT_SIZE_STEP)))
            for widget in (meno, value, piu):
                controls.add_widget(widget)
            content.add_widget(auto)
            content.add_widget(Label(text="Manuale", size_hint_y=None,
                                     height=dp(profile.tokens.typography["caption"] + 8)))
            content.add_widget(controls)
            popup.open()
            return popup

        def _testo_numerico(self):
            current = testo_corrente()
            return int(round(_ui_profile().tokens.typography["body"])) if current == "auto" else current

        def _applica_testo_corrente(self):
            profile = _ui_profile()
            applica_tema(profile)
            configura_tema_md(self.theme_cls, profile)
            if hasattr(self, "_testo_btn"):
                self._testo_btn.text = etichetta_testo()
            if self._view_kind == "home":
                status = self.status.text
                self._costruisce_home()
                self.show_home()
                self.status.text = status
            elif self._view_kind == "readonly" and self._readonly_scheda is not None:
                self._mostra_lettura(self._readonly_remote, self._readonly_scheda)
            else:
                current = self.stack.children[0] if self.stack.children else None
                if current is not None and hasattr(current, "apply_text_profile"):
                    current.apply_text_profile()
                aggiorna_testo_widget(self.stack, profile)

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
            profile = _ui_profile()
            for remote in self._ultime_schede:
                row = BoxLayout(size_hint_y=None, height=dp(profile.touch_target + 16), spacing=dp(6),
                                 padding=dp(profile.tokens.spacing["xs"]))
                open_button = Button(text=f"{remote.name}   —   {remote.modified_time}")
                open_button.bind(on_release=lambda _, item=remote: self.open(item))
                delete = Button(text="Elimina", size_hint_x=None,
                                width=dp(profile.touch_target * 2.2))
                delete.background_color = hex_to_rgba(profile.tokens.colors["error_container"])
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
            self._mostra_lettura(remote, scheda)

        def _mostra_lettura(self, remote, scheda):
            self._editor_view = None
            self._view_kind = "readonly"
            self._readonly_remote = remote
            self._readonly_scheda = scheda
            profile = _ui_profile()
            root = BoxLayout(orientation="vertical", padding=dp(profile.tokens.spacing["md"]),
                             spacing=dp(profile.tokens.spacing["sm"]))
            bar = BoxLayout(size_hint_y=None,
                            height=dp(profile.tokens.dimensions["toolbar_height"]),
                            spacing=dp(profile.tokens.spacing["sm"]))
            menu = Button(text="Menu", size_hint_x=None,
                          width=dp(profile.touch_target * 1.7))
            menu.bind(on_release=lambda *_: self.apri_menu())
            back = Button(text="< Lista", size_hint_x=None,
                          width=dp(profile.touch_target * 2.5))
            back.bind(on_release=lambda *_: self._lista_aggiornata())
            edit = Button(text="Modifica")
            edit.bind(on_release=lambda *_: self.edit(remote))
            workout = Button(text="Allenati")
            workout.bind(on_release=lambda *_: self.open_workout(remote))
            bar.add_widget(menu)
            bar.add_widget(back)
            bar.add_widget(edit)
            bar.add_widget(workout)
            scroll, contenuto = _area_scrollabile(spacing=dp(profile.tokens.spacing["md"]))
            gruppo_corrente = object()
            for exercise in scheda.exercises:
                gruppo = (exercise.group or "").strip()
                if gruppo != gruppo_corrente:
                    gruppo_corrente = gruppo
                    if gruppo:
                        sezione = markup_px(profile, profile.tokens.typography["section"],
                                            correction=1.2)
                        accent = profile.tokens.colors["accent"].lstrip("#")
                        contenuto.add_widget(_label_righe(
                            f"[b][color={accent}][size={sezione}]"
                            f"{escape_markup(gruppo.upper())}[/size][/color][/b]", contenuto))
                contenuto.add_widget(self._card_lettura(exercise))
            root.add_widget(bar)
            root.add_widget(scroll)
            self.stack.clear_widgets()
            self.stack.add_widget(root)

        def _lista_aggiornata(self):
            self._dispose_current_view()
            self.show_home()
            self.refresh()

        def _card_lettura(self, exercise):
            profile = _ui_profile()
            model = readonly_card(exercise, profile)
            tokens = profile.tokens
            # Markup [size=N] is in pixels: convert the dp token by the window
            # density, otherwise text renders 2-3x too small on Android.
            body = markup_px(profile, tokens.typography["body"], correction=1.2)
            title = markup_px(profile, tokens.typography["body"] + 4, correction=1.2)
            detail = markup_px(profile, tokens.typography["body"] + 1, correction=1.2)
            accent = tokens.colors["accent"].lstrip("#")
            muted = tokens.colors["muted"].lstrip("#")
            card = MDCard(orientation="vertical", size_hint_y=None, style="filled",
                          theme_bg_color="Custom",
                          md_bg_color=hex_to_rgba(tokens.colors["surface_container"]),
                          radius=[dp(tokens.dimensions["card_radius"])],
                          spacing=dp(tokens.spacing["xs"]), padding=dp(tokens.spacing["sm"]))
            card.bind(minimum_height=card.setter("height"))
            titolo = (f"[b][size={title}]{escape_markup(exercise.name or '(senza nome)')}"
                      "[/size][/b]")
            if exercise.repetitions:
                titolo += f"   [size={detail}]{escape_markup(exercise.repetitions)}[/size]"
            if exercise.recovery:
                titolo += (f"   [size={detail}][color={accent}]"
                           f"{escape_markup(exercise.recovery)}[/color][/size]")
            card.add_widget(_label_righe(titolo, card))
            if (exercise.explanation or "").strip():
                card.add_widget(_label_righe(
                    f"[color={muted}][size={body}]{escape_markup(exercise.explanation)}"
                    "[/size][/color]", card))
            if (exercise.notes or "").strip():
                card.add_widget(_label_righe(
                    f"[i][color={muted}][size={body}]Note: {escape_markup(exercise.notes)}"
                    "[/size][/color][/i]", card))
            frames = BoxLayout(orientation=model.frame_axis, size_hint_y=None,
                               height=dp(tokens.dimensions["frame_min_height"] * 2), spacing=dp(6))
            for percorso in (exercise.frame_start, exercise.frame_finish):
                if percorso:
                    image = Image(source=percorso, fit_mode="contain")
                    tap_key = f"frame-tap-{id(image)}"

                    def tap_down(widget, touch, key=tap_key):
                        if widget.collide_point(*touch.pos):
                            touch.ud[key] = touch.pos

                    def tap_up(widget, touch, path=percorso, key=tap_key):
                        origin = touch.ud.pop(key, None)
                        if origin is None or not widget.collide_point(*touch.pos):
                            return False
                        moved = (touch.x - origin[0]) ** 2 + (touch.y - origin[1]) ** 2
                        if moved > dp(12) ** 2:
                            return False
                        self._apri_frame_fullscreen(
                            path, exercise.frame_start, exercise.frame_finish)
                        return True

                    image.bind(on_touch_down=tap_down, on_touch_up=tap_up)
                    frames.add_widget(image)
                else:
                    vuoto = BoxLayout()
                    vuoto.add_widget(Label(text="frame non estratto",
                                            font_size=sp(tokens.typography["caption"]),
                                           color=hex_to_rgba(tokens.colors["muted"])))
                    frames.add_widget(vuoto)
            card.add_widget(frames)
            return card

        def _apri_frame_fullscreen(self, percorso, start, finish):
            pairs = [(etichetta, frame) for etichetta, frame in
                     (("START", start), ("FINISH", finish)) if frame]
            if not pairs:
                return
            profile = _ui_profile()
            content = BoxLayout(orientation="vertical",
                                spacing=dp(profile.tokens.spacing["sm"]),
                                padding=dp(4))
            image = Image(source=percorso or pairs[0][1], fit_mode="contain")
            content.add_widget(image)
            popup = Popup(title="Frame START / FINISH", content=content,
                          size_hint=(0.98, 0.95), auto_dismiss=True)
            row = BoxLayout(size_hint_y=None,
                            height=dp(profile.touch_target + 16), spacing=dp(8))
            for etichetta, frame in pairs:
                bottone = Button(text=etichetta, size_hint_x=None,
                                 width=dp(profile.touch_target * 2.2))
                bottone.bind(on_release=lambda _, p=frame: setattr(image, "source", p))
                row.add_widget(bottone)
            chiudi = Button(text="Chiudi")
            chiudi.bind(on_release=lambda *_: popup.dismiss())
            row.add_widget(chiudi)
            content.add_widget(row)
            popup.open()

        def open_workout(self, remote):
            try:
                esercizi = controller.open_for_workout(remote)
            except HomeUnavailableError as exc:
                self.status.text = str(exc)
                return
            session = WorkoutSessionController(esercizi)
            self.stack.clear_widgets()
            self._view_kind = "workout"
            self.stack.add_widget(WorkoutScreen(session,
                                                on_back=lambda: self._torna_in_lettura(remote),
                                                on_menu=self.apri_menu))

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
