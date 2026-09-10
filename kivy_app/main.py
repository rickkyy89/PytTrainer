"""Kivy UI entry point. Import this module only where Kivy is installed."""

from __future__ import annotations

from pathlib import Path
import sys

from core.platform import LocalCredentialsProvider

from .config import FolderConfigStore
from .controller import DriveHomeController, HomeUnavailableError


def handle_close_request(current, editor_view, finish_close) -> bool:
    """Coordinate Android/desktop close without depending on Kivy classes."""
    if bool(getattr(current, "busy", False)):
        return True
    if editor_view is not None and editor_view.modifiche_non_salvate:
        editor_view.richiedi_uscita(on_continue=finish_close)
        return True
    return False


def build_controller(
    base_dir: str | Path | None = None, *, is_android: bool | None = None,
    android_bridge_factory=None, local_store=None, prefs_store=None,
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
        base_dir=base, local_store=local_store, prefs_store=prefs_store,
    )


def build_pc_controller(base_dir: str | Path | None = None) -> DriveHomeController:
    """Compose the unchanged PC OAuth implementation."""
    return build_controller(base_dir, is_android=False)


def duplicate_default_name(sheet_name: str) -> str:
    """Sensible name pre-filled in the duplicate dialog, without extension."""
    stem = sheet_name[: -len(".scheda")] if sheet_name.endswith(".scheda") else sheet_name
    return f"{stem} (copia)"


def pc_icon_path() -> Path:
    """Return the tracked PC icon independently of the current directory."""
    return Path(__file__).resolve().parent.parent / "assets" / "pc" / "icon.ico"


def configure_pc_window_icon() -> None:
    """Configure Kivy's PC window icon before the window is created."""
    if sys.platform == "android":
        return
    from kivy.config import Config

    Config.set("kivy", "window_icon", str(pc_icon_path()))


def run() -> None:
    """Run the small PC Kivy shell without exposing Kivy to pytest imports."""
    configure_pc_window_icon()
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

    from .config import FolderConfigStore, LocalPrefsStore
    from .controller import DriveHomeController, HomeUnavailableError
    from .editor_screen import EditorScreen
    from .export import DocExportController
    from .export_screen import ExportScreen
    from .file_picker import choose_file, choose_save_file
    from .media import MediaFlowController
    from .media_screen import MediaScreen
    from .workout import WorkoutSessionController
    from .workout_screen import WorkoutScreen
    from .home_layout import HOME_MENU_LABELS, etichetta_recupero, home_toolbar_rows, readonly_card
    from .material import (ScalePreferenceStore, hex_to_rgba, imposta_pulsanti,
                           imposta_spessore_penna, imposta_testo, markup_px,
                           profile_for_window)
    from .theme import applica_tema, aggiorna_testo_widget, configura_tema_md
    from .compact_menu import apri_menu
    from .snackbar import mostra_snackbar
    from .launcher import apri_url, ultimo_errore, url_cartella_drive
    from .version import version_label

    base_dir = Path(__file__).resolve().parent.parent
    prefs_store = LocalPrefsStore(base_dir / "local-save.json")
    local_store = None
    if sys.platform == "android":
        from .local_store import AndroidLocalStore
        local_store = AndroidLocalStore(kind=prefs_store.load().destinazione)
    controller = build_controller(base_dir, local_store=local_store, prefs_store=prefs_store)
    scala_store = ScalePreferenceStore(controller.base_dir / "ui-preferences.json")
    scala_store.migrate_legacy()
    imposta_pulsanti(scala_store.load_button_preset())
    imposta_testo(scala_store.load_text())
    imposta_spessore_penna(scala_store.load_pen_width())
    if sys.platform == "android":
        from .platform_android import AndroidFrameExtractor, AndroidExportGuard, android_pdf_cache_dir
        media_backend = AndroidFrameExtractor()
        pdf_cache_dir = android_pdf_cache_dir()
        export_guard = AndroidExportGuard()
    else:
        from core.platform import PcFfmpegBackend
        media_backend = PcFfmpegBackend()
        pdf_cache_dir = None
        export_guard = None

    def _label_righe(testo, contenitore, *, font_size=None, **kw):
        if font_size is not None:
            kw["font_size"] = font_size
        label = Label(text=testo, markup=True, halign="left", valign="top",
                      size_hint_y=None, **kw)
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
            self._settings_return = None
            self._costruisce_home()
            Window.bind(on_request_close=self._on_request_close)
            Window.bind(size=self._on_window_size)
            self.show_home()
            return self.stack

        def on_pause(self):
            # Su Android il default (None) e' falsy: Kivy risponde chiudendo
            # l'attivita' (finishAndRemoveTask) appena l'app va in background,
            # che e' il "crash" al sleep del tablet. Restituire True permette
            # all'app di restare in memoria e riprendere con on_resume.
            return True

        def on_resume(self):
            # The transport refreshes a rejected native token, including saves.
            pass

        def _costruisce_home(self):
            profile = _ui_profile()
            applica_tema(profile)
            configura_tema_md(self.theme_cls, profile)
            tokens = profile.tokens
            self.home = BoxLayout(orientation="vertical", spacing=dp(tokens.spacing["sm"]))
            self.home.add_widget(self._app_bar("Home"))
            content = BoxLayout(orientation="vertical", padding=dp(tokens.spacing["md"]),
                                spacing=dp(tokens.spacing["sm"]))
            self.home.add_widget(content)
            refresh = Button(text="Aggiorna")
            refresh.bind(on_release=lambda *_: self.refresh())
            create = Button(text="Nuova scheda")
            create.background_color = hex_to_rgba(tokens.colors["coral"])
            create.color = hex_to_rgba(tokens.colors["on_coral"])
            create.bind(on_release=lambda *_: self.create_dialog())
            azioni = {"refresh": refresh, "create": create}
            self.status = Label(text="Premi Aggiorna per caricare le schede.",
                                size_hint_y=None, height=40, halign="left", valign="middle")
            self.status.bind(
                width=lambda _, v: setattr(self.status, "text_size", (v, None)))
            self.status.bind(
                texture_size=lambda l, ts: setattr(l, "height", max(ts[1], 40)))
            content.add_widget(self.status)
            self.home_body = BoxLayout(orientation="vertical", spacing=8)
            content.add_widget(self.home_body)
            footer = Label(text=version_label(), size_hint_y=None,
                           height=dp(max(tokens.typography["caption"] + 6, 22)),
                            font_size=sp(tokens.typography["caption"]),
                           color=hex_to_rgba(tokens.colors["muted"]), halign="right")
            footer.bind(width=lambda _, value: setattr(footer, "text_size", (value, None)))
            content.add_widget(footer)
            toolbar = BoxLayout(size_hint_y=None, height=dp(profile.touch_target),
                                spacing=dp(tokens.spacing["xs"]),
                                padding=(dp(tokens.spacing["md"]), 0,
                                         dp(tokens.spacing["md"]), 0))
            for nome in home_toolbar_rows(profile)[0]:
                toolbar.add_widget(azioni[nome])
            self.home.add_widget(toolbar)

        def _app_bar(self, title, *, on_back=None):
            profile = _ui_profile()
            bar = BoxLayout(size_hint_y=None, height=dp(profile.touch_target), spacing=dp(8),
                            padding=(dp(8), 0, dp(8), 0))
            if on_back is not None:
                back = Button(text="‹", size_hint_x=None, width=dp(profile.touch_target))
                back.bind(on_release=lambda *_: on_back())
                bar.add_widget(back)
            label = Label(text=title, halign="left", shorten=True)
            label.bind(width=lambda widget, value: setattr(
                widget, "text_size", (value, widget.height)))
            bar.add_widget(label)
            menu = Button(text="⋮", size_hint_x=None, width=dp(profile.touch_target))
            menu.bind(on_release=lambda anchor: self.apri_menu(anchor=anchor))
            bar.add_widget(menu)
            return bar

        def _info(self, text):
            if hasattr(self, "status"):
                self.status.text = text
            # Window overlay keeps transient feedback out of navigation stacks.
            mostra_snackbar(Window, text)

        def _error(self, error, *, prefix=""):
            text = f"{prefix}{error}"
            Popup(title="Errore", content=Label(text=text),
                  size_hint=(0.86, None), height=dp(190)).open()

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
            self._info(message)

        def edit(self, remote):
            try:
                editor = controller.open_for_edit(remote)
            except HomeUnavailableError as exc:
                self._error(exc)
                return
            self.show_editor(remote, editor)

        def apri_locale(self):
            """Pick a .scheda on the device (or Documents/Download) and edit it."""
            def scelto(percorso):
                if not percorso:
                    return
                try:
                    editor = controller.open_for_edit_locale(percorso)
                except Exception as exc:
                    self._error(exc, prefix="Impossibile aprire il file: ")
                    return
                self.show_editor(None, editor, on_back=self.go_home)
            choose_file(scelto, title="Apri scheda locale",
                        patterns=[("Scheda pyTrainer", "*.scheda")])

        def csv_ai(self):
            """Save the example CSV in Downloads and copy the AI prompt to clipboard."""
            from .ai_csv import PROMPT_TEMPLATE
            try:
                percorso = controller.salva_csv_esempio()
            except Exception as exc:
                self._error(exc, prefix="CSV di esempio non salvato: ")
                return
            appunti_ok = True
            try:
                from kivy.core.clipboard import Clipboard
                Clipboard.copy(PROMPT_TEMPLATE)
            except Exception:
                appunti_ok = False
            self._info(
                f"CSV esempio in {percorso}; prompt per l'AI "
                + ("copiato negli appunti." if appunti_ok else "NON copiabile qui.")
            )
            profile = _ui_profile()
            passi = [
                ("Prompt copiato negli appunti." if appunti_ok else
                 "Attenzione: prompt non copiato, riscrivilo dal CSV di esempio."),
                f"CSV di esempio salvato in: {percorso}",
                "1. Incolla il prompt in Gemini, ChatGPT o un'altra AI e, subito dopo, "
                "descrivi la scheda che vuoi (distretti, livello, attrezzi, durata, "
                "numero di esercizi): piu sei preciso, piu la scheda sara su misura.",
                "2. Salva su file il CSV che l'AI ti restituisce, senza modificarlo.",
                "3. Torna in pyTrainer: \"Nuova scheda\", aprila, poi dal menu \"Importa "
                "CSV\" > \"Da file locale\" scegli il CSV generato.",
            ]
            scroll, contenuto = _area_scrollabile(spacing=dp(profile.tokens.spacing["sm"]))
            for testo in passi:
                contenuto.add_widget(_label_righe(escape_markup(testo), contenuto))
            chiudi = Button(text="Ho capito", size_hint=(0.6, None),
                            height=dp(profile.touch_target))
            popup = Popup(title="Crea una scheda con l'AI", content=scroll,
                          size_hint=(0.94, 0.8), auto_dismiss=True)
            contenuto.add_widget(chiudi)
            chiudi.bind(on_release=lambda *_: popup.dismiss())
            popup.open()
            return popup

        def show_editor(self, remote, editor, *, on_back=None):
            self.stack.clear_widgets()
            self._view_kind = "editor"
            back = on_back or (lambda: self._torna_in_lettura(remote))
            riapri = lambda: self.show_editor(remote, editor, on_back=back)
            self._editor_view = EditorScreen(
                controller, editor, remote,
                on_back=back,
                open_media=lambda ed, i: self.open_media(riapri, ed, i),
                on_export=lambda ed: self.open_export(riapri, ed),
                on_conflict_exit=self.go_home_message,
                on_menu=self.open_settings_from_screen,
            )
            self.stack.add_widget(self._editor_view)

        def _on_request_close(self, *_):
            current = self.stack.children[0] if self.stack.children else None
            return handle_close_request(current, self._editor_view, self._finish_close)

        def _finish_close(self):
            """Continuation used only after Save or Discard; Stay never calls it."""
            self.stop()

        def _torna_in_lettura(self, remote):
            self._apri_in_lettura(remote)

        def open_export(self, riapri, editor):
            try:
                export = DocExportController(
                    editor, credential_provider=controller.credential_provider,
                    base_dir=controller.base_dir, pdf_cache_dir=pdf_cache_dir,
                    background_guard=export_guard,
                )
            except Exception as exc:
                self._error(exc, prefix="Impossibile aprire Esporta: ")
                return
            self.stack.clear_widgets()
            self._view_kind = "export"
            self.stack.add_widget(ExportScreen(
                export, on_back=riapri, on_menu=self.open_settings_from_screen))

        def open_media(self, riapri, editor, indice):
            try:
                output_dir = editor.output_frames()
                media = MediaFlowController(
                    editor.esercizi[indice], output_dir,
                    backend=media_backend,
                    transaction=lambda operation: editor.transazione_media(
                        operation, output_dir=output_dir),
                )
            except Exception as exc:  # EditorValidationError e simili
                self._error(exc, prefix="Impossibile aprire Video e frame: ")
                return
            self.stack.clear_widgets()
            self._view_kind = "media"
            self.stack.add_widget(MediaScreen(
                media, on_back=riapri, on_menu=self.open_settings_from_screen))

        def open_settings_from_screen(self, anchor=None):
            """Child contextual menus already selected Settings: do not open a second menu."""
            del anchor
            return self.show_settings()

        def apri_menu(self, anchor=None):
            if self._view_kind == "home":
                callbacks = (self.csv_ai, self.apri_locale,
                             self.apri_cartella_drive, self.show_settings)
                actions = tuple(zip(HOME_MENU_LABELS, callbacks))
            else:
                actions = (("Impostazioni", self.show_settings),)
            return apri_menu(actions, anchor=anchor)

        def apri_cartella_drive(self):
            """Open the selected Drive folder and expose launcher failures in Home."""
            url = url_cartella_drive(controller.folder_config.current_folder_id)
            if apri_url(url):
                self._info("Cartella Drive aperta.")
            else:
                dettaglio = ultimo_errore() or "il launcher non ha aperto l'URL"
                self._error(dettaglio, prefix="Impossibile aprire la cartella Drive: ")

        def _azione_da_home(self, action):
            if self._view_kind != "home":
                self._dispose_current_view()
                self.show_home()
            action()

        def _dispose_current_view(self):
            current = self.stack.children[0] if self.stack.children else None
            if current is not None and hasattr(current, "dispose"):
                current.dispose()

        def _applica_testo_corrente(self):
            profile = _ui_profile()
            applica_tema(profile)
            configura_tema_md(self.theme_cls, profile)
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

        def show_settings(self):
            from .settings_screen import SettingsScreen

            if self._view_kind == "settings":
                return
            previous = self.stack.children[0] if self.stack.children else self.home
            self._settings_return = (self._view_kind, previous)
            self._settings_style_changed = False
            self._view_kind = "settings"
            self.stack.clear_widgets()
            self._settings_view = SettingsScreen(
                controller, scala_store, on_back=self._return_from_settings,
                on_text=self._set_text, on_buttons=self._set_buttons,
                on_pen=self._set_pen, on_destination=self._set_destination,
                on_folder_change=self._folder_configuration_changed,
                local_destination_available=local_store is not None,
            )
            self.stack.add_widget(self._settings_view)
            self._refresh_folder_names_async()

        def _return_from_settings(self):
            if not self._settings_return:
                self.show_home()
                return
            kind, previous = self._settings_return
            self._settings_return = None
            self.stack.clear_widgets()
            self.stack.add_widget(previous)
            self._view_kind = kind
            from .settings_layout import settings_return_action
            action = settings_return_action(
                kind, getattr(self, "_settings_style_changed", False))
            if action != "retain":
                self._apply_style_to_returned_view(kind, previous)

        def _apply_style_to_returned_view(self, kind, previous):
            """Apply persisted style without replacing stateful editor-like views."""
            profile = _ui_profile()
            applica_tema(profile)
            configura_tema_md(self.theme_cls, profile)
            if kind == "home":
                status = self.status.text
                scroll_y = self.home_body.children[0].scroll_y if self.home_body.children else 1
                self._costruisce_home()
                self.stack.clear_widgets()
                self.stack.add_widget(self.home)
                self._render_lista()
                self.status.text = status
                if self.home_body.children:
                    self.home_body.children[0].scroll_y = scroll_y
            elif kind == "readonly" and self._readonly_scheda is not None:
                self._mostra_lettura(self._readonly_remote, self._readonly_scheda)
            else:
                if hasattr(previous, "apply_text_profile"):
                    previous.apply_text_profile()
                aggiorna_testo_widget(previous, profile)

        def _refresh_folder_names_async(self):
            """Render cached labels first, then enrich them off the Kivy thread."""
            import threading
            from kivy.clock import Clock

            def worker():
                controller.refresh_folder_names(attempts=3)
                Clock.schedule_once(lambda *_: self._folder_names_refreshed(), 0)

            threading.Thread(target=worker, name="drive-folder-names", daemon=True).start()

        def _folder_names_refreshed(self):
            if self._view_kind == "settings":
                if getattr(self._settings_view, "slider_active", False):
                    from kivy.clock import Clock
                    Clock.schedule_once(lambda *_: self._folder_names_refreshed(), 0.2)
                    return
                self._rebuild_settings()

        def _folder_configuration_changed(self):
            self._rebuild_settings()
            self._refresh_folder_names_async()

        def _rebuild_settings(self):
            scroll_y = getattr(getattr(self, "_settings_view", None), "scroll", None)
            scroll_y = getattr(scroll_y, "scroll_y", 1)
            from .settings_screen import SettingsScreen
            self.stack.clear_widgets()
            self._settings_view = SettingsScreen(
                controller, scala_store, on_back=self._return_from_settings,
                on_text=self._set_text, on_buttons=self._set_buttons,
                on_pen=self._set_pen, on_destination=self._set_destination,
                on_folder_change=self._folder_configuration_changed,
                local_destination_available=local_store is not None,
            )
            self._settings_view.scroll.scroll_y = scroll_y
            self.stack.add_widget(self._settings_view)

        def _set_text(self, value):
            scala_store.save_text(imposta_testo(value))
            self._settings_style_changed = True
            profile = _ui_profile()
            applica_tema(profile)
            configura_tema_md(self.theme_cls, profile)
            # Do not replace the Slider while it owns an active touch.
            aggiorna_testo_widget(self._settings_view, profile)

        def _set_buttons(self, value):
            scala_store.save_button_preset(imposta_pulsanti(value))
            self._settings_style_changed = True
            self._rebuild_settings()

        def _set_pen(self, value):
            scala_store.save_pen_width(imposta_spessore_penna(value))

        def _set_destination(self, value):
            controller.imposta_destinazione_locale(value)
            self._rebuild_settings()

        def _on_window_size(self, *_):
            # Kivy dispatches continuously during desktop resize/orientation.
            # Rebuild only layout-sensitive, read-only surfaces and retain scroll.
            from kivy.clock import Clock
            Clock.unschedule(self._reflow_current)
            Clock.schedule_once(self._reflow_current, 0)

        def _reflow_current(self, *_):
            if self._view_kind == "home":
                status = self.status.text
                old_scroll = self.home_body.children[0].scroll_y if self.home_body.children else 1
                self._costruisce_home()
                self.show_home()
                self.status.text = status
                if self.home_body.children:
                    self.home_body.children[0].scroll_y = old_scroll
            elif self._view_kind == "readonly" and self._readonly_scheda is not None:
                self._mostra_lettura(self._readonly_remote, self._readonly_scheda)
            elif self._view_kind == "settings":
                self._rebuild_settings()

        def refresh(self):
            try:
                records = controller.refresh()
            except HomeUnavailableError as exc:
                self._error(exc)
                return
            self._ultime_schede = records
            self._info(f"{len(records)} schede nella cartella corrente.")
            self._render_lista()

        def _render_lista(self):
            self.home_body.clear_widgets()
            scroll, contenuto = _area_scrollabile()
            self.home_body.add_widget(scroll)
            profile = _ui_profile()
            for remote in self._ultime_schede:
                row = BoxLayout(size_hint_y=None, height=dp(profile.touch_target + 16), spacing=dp(6),
                                 padding=dp(profile.tokens.spacing["xs"]))
                open_button = Button(text=f"{remote.name}   —   {remote.modified_time}",
                                     halign="left", valign="middle", shorten=True)
                open_button.bind(width=lambda _, v, b=open_button,
                                 h=profile.touch_target + 16:
                                 setattr(b, "text_size", (max(v - dp(20), 10), dp(h))))
                open_button.bind(on_release=lambda _, item=remote: self.open(item))
                context = Button(text="⋮", size_hint_x=None, width=dp(profile.touch_target))
                context.bind(on_release=lambda anchor, item=remote:
                             self._row_menu(item, anchor))
                row.add_widget(open_button)
                row.add_widget(context)
                contenuto.add_widget(row)

        def _row_menu(self, remote, anchor=None):
            return apri_menu((
                ("Duplica", lambda: self.duplicate_dialog(remote)),
                ("Elimina", lambda: self.confirm_delete(remote)),
            ), anchor=anchor)

        def open(self, remote):
            try:
                conflitto = controller.check_conflict(remote)
            except HomeUnavailableError as exc:
                self._error(exc)
                return
            if conflitto is not None:
                def esito(choice, risultato):
                    if isinstance(risultato, Exception):
                        self._error(risultato)
                        return
                    self._info({
                        "locale": "Conflitto risolto con la versione locale.",
                        "remota": "Conflitto risolto con la versione remota.",
                        "duplicata": "Versione locale duplicata su Drive.",
                    }[choice])
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
                self._error(exc)
                return
            message = f"{scheda.name}: sola lettura"
            if getattr(controller, "avvertenza", None):
                message += f" — {controller.avvertenza}"
            self._info(message)
            self._mostra_lettura(remote, scheda)

        def _mostra_lettura(self, remote, scheda):
            previous_scroll = getattr(getattr(self, "_readonly_scroll", None), "scroll_y", 1)
            self._editor_view = None
            self._view_kind = "readonly"
            self._readonly_remote = remote
            self._readonly_scheda = scheda
            profile = _ui_profile()
            root = BoxLayout(orientation="vertical", spacing=dp(profile.tokens.spacing["sm"]))
            title = Path(scheda.name).stem
            root.add_widget(self._app_bar(title, on_back=self.show_home))
            content = BoxLayout(orientation="vertical", padding=dp(profile.tokens.spacing["md"]),
                                spacing=dp(profile.tokens.spacing["sm"]))
            edit = Button(text="Modifica")
            edit.bind(on_release=lambda *_: self.edit(remote))
            workout = Button(text="Allenati")
            workout.bind(on_release=lambda *_: self.open_workout(remote))
            scroll, contenuto = _area_scrollabile(spacing=dp(profile.tokens.spacing["md"]))
            self._readonly_scroll = scroll
            scroll.scroll_y = previous_scroll
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
            content.add_widget(scroll)
            root.add_widget(content)
            bottom = BoxLayout(size_hint_y=None, height=dp(profile.touch_target), spacing=dp(8),
                               padding=(dp(12), 0, dp(12), 0))
            bottom.add_widget(edit)
            bottom.add_widget(workout)
            root.add_widget(bottom)
            self.stack.clear_widgets()
            self.stack.add_widget(root)

        def _lista_aggiornata(self):
            self._dispose_current_view()
            self.show_home()

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
                           f"{escape_markup(etichetta_recupero(exercise.recovery))}[/color][/size]")
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
                self._error(exc)
                return
            session = WorkoutSessionController(esercizi)
            self.stack.clear_widgets()
            self._view_kind = "workout"
            self.stack.add_widget(WorkoutScreen(session,
                                                on_back=lambda: self._torna_in_lettura(remote),
                                                on_menu=self.open_settings_from_screen))

        def _dialogo_nome(self, titolo, etichetta_conferma, nome_predefinito, on_conferma):
            """Name popup with Enter submission and explicit confirm/cancel buttons."""
            profile = _ui_profile()
            content = BoxLayout(orientation="vertical",
                                spacing=dp(profile.tokens.spacing["sm"]))
            input_name = TextInput(hint_text="Nome scheda", text=nome_predefinito,
                                   multiline=False)
            buttons = BoxLayout(size_hint_y=None, height=dp(profile.touch_target),
                                spacing=dp(profile.tokens.spacing["sm"]))
            popup = Popup(title=titolo, content=content, size_hint=(0.8, 0.35))

            def submit(*_):
                popup.dismiss()
                on_conferma(input_name.text)

            annulla = Button(text="Annulla")
            conferma = Button(text=etichetta_conferma)
            conferma.background_color = hex_to_rgba(profile.tokens.colors["coral"])
            conferma.color = hex_to_rgba(profile.tokens.colors["on_coral"])
            annulla.bind(on_release=lambda *_: popup.dismiss())
            conferma.bind(on_release=submit)
            input_name.bind(on_text_validate=submit)
            buttons.add_widget(annulla)
            buttons.add_widget(conferma)
            content.add_widget(input_name)
            content.add_widget(buttons)
            popup.open()
            return popup

        def create_dialog(self):
            return self._dialogo_nome("Nuova scheda", "Crea", "", self.create)

        def create(self, name):
            try:
                creata = controller.create(name)
                self._info(f"Scheda creata: {creata.name}. Premi Aggiorna per caricarla.")
            except HomeUnavailableError as exc:
                self._error(exc)

        def duplicate_dialog(self, remote):
            return self._dialogo_nome(
                f"Duplica {remote.name}", "Duplica", duplicate_default_name(remote.name),
                lambda nome: self.duplicate(remote, nome))

        def duplicate(self, remote, new_name):
            try:
                creata = controller.duplicate(remote, new_name)
            except HomeUnavailableError as exc:
                self._error(exc)
                return
            self._info(f"Scheda duplicata come {creata.name}. Premi Aggiorna per caricarla.")
            if getattr(controller, "avvertenza", None):
                self.status.text += f" — {controller.avvertenza}"

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
                self._ultime_schede = [item for item in self._ultime_schede if item.id != remote.id]
                self._render_lista()
                self._info("Scheda eliminata.")
            except HomeUnavailableError as exc:
                self._error(exc)

    PyTrainerApp().run()


if __name__ == "__main__":
    run()
