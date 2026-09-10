"""Kivy screen for editing one opened scheda (ticket 06).

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
All domain behavior lives in ``kivy_app.editor.SchedaEditorController``;
this module only renders and forwards events.
"""

from __future__ import annotations

import math
import inspect
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core.drive_sync import SyncConflict

from .compact_menu import apri_menu
from .editor import EditorValidationError
from .file_picker import choose_file, choose_save_file
from .editor_layout import (
    editor_global_actions,
    editor_layout,
    exercise_context_actions,
    field_columns,
)
from .material import profile_for_window
from .snackbar import mostra_snackbar


CAMPI_BREVI = (("nome", "Nome"), ("gruppo", "Gruppo"),
               ("ripetizioni", "Ripetizioni"), ("recupero", "Recupero"))
CAMPI_LUNGHI = (("spiegazione", "Spiegazione"), ("note", "Note"))


class EditorScreen(BoxLayout):
    def __init__(self, controller, editor, remote, on_back, open_media=None, on_export=None,
                 on_conflict_exit=None, on_menu=None):
        super().__init__(orientation="vertical", padding=10, spacing=6)
        self._controller = controller
        self._editor = editor
        self._remote = remote
        self._on_back = on_back
        self._open_media = open_media
        self._on_export = on_export
        self._on_conflict_exit = on_conflict_exit or (lambda message: self._on_back())
        self._on_menu = on_menu
        self._fields = []
        self._open_index = 0
        self._saving = False
        self._disposed = False
        self._target_h = dp(profile_for_window(Window).touch_target)

        # Uniform app bar: navigation, title and one editor overflow.
        self.header = BoxLayout(size_hint_y=None, height=self._target_h, spacing=dp(8))
        self._back = self._button(text="‹", size_hint=(None, None),
                            width=self._target_h, height=self._target_h)
        self._back.bind(on_release=lambda *_: self.richiedi_uscita())
        titolo = self._editor.titolo or Path(self._editor.percorso_bundle).stem or "Editor"
        self.title = Label(text=titolo, halign="left", valign="middle",
                           shorten=True, shorten_from="right")
        self.title.bind(width=lambda _, v: setattr(self.title, "text_size", (v, self.title.height)))
        self._menu = self._button(text="⋮", size_hint=(None, None),
                            width=self._target_h, height=self._target_h)
        self._menu.bind(on_release=lambda button: self._open_editor_menu(button))
        self.header.add_widget(self._back)
        self.header.add_widget(self.title)
        self.header.add_widget(self._menu)
        self.add_widget(self.header)

        self.status = Label(text="", size_hint_y=None, height=dp(28),
                            halign="left", valign="middle", shorten=True,
                            shorten_from="right")
        self.status.bind(
            width=lambda _, v: setattr(self.status, "text_size", (v, self.status.height)))
        self.add_widget(self.status)
        Window.bind(on_key_down=self._on_key_down)

        self.rows = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self._scroll = ScrollView()
        self._scroll.add_widget(self.rows)
        self.add_widget(self._scroll)

        # The four primary actions stay reachable while the form scrolls.
        action_bar = BoxLayout(size_hint_y=None, height=self._target_h, spacing=dp(8))
        undo_bar = self._button(text="↶ Annulla")
        undo_bar.bind(on_release=lambda *_: self._wrap(self._editor.undo, rebuild=True))
        redo_bar = self._button(text="↷ Ripeti")
        redo_bar.bind(on_release=lambda *_: self._wrap(self._editor.redo, rebuild=True))
        save_bar = self._button(text="▣ Salva")
        save_bar.bind(on_release=lambda *_: self.apri_salvataggio())
        add_bar = self._button(text="＋ Aggiungi")
        add_bar.bind(on_release=lambda *_: self._wrap(self._editor.aggiungi, rebuild=True))
        for button in (undo_bar, redo_bar, save_bar, add_bar):
            action_bar.add_widget(button)
        self.add_widget(action_bar)

        self._rebuild()

    @property
    def modifiche_non_salvate(self):
        return self._editor.sporco

    def _rebuild(self):
        self._commit_active_field()
        self.rows.clear_widgets()
        self._fields.clear()
        for indice, esercizio in enumerate(self._editor.esercizi):
            self.rows.add_widget(self._exercise_block(indice, esercizio))
        self._refresh_status()

    def _open_editor_menu(self, anchor):
        if not self._ready_for_action():
            return None
        self._commit_active_field()
        callbacks = {
            "Importa CSV": self._import_csv,
            "Importa da scheda": self._import_scheda,
            "Genera Google Doc": self._export_document,
            "Impostazioni": lambda: self.richiedi_uscita(
                lambda: self._invoke_parent_menu(anchor, action="settings")),
        }
        labels = editor_global_actions(include_parent=self._on_menu is not None)
        return apri_menu(tuple((label, callbacks[label]) for label in labels), anchor=anchor)

    def _invoke_parent_menu(self, anchor, *, action=None):
        """Invoke the parent context contract, with a legacy direct fallback."""
        if self._on_menu is None:
            return None
        signature = None
        try:
            signature = inspect.signature(self._on_menu)
        except (TypeError, ValueError):
            pass
        if action and signature is not None:
            for action_name in ("action", "azione"):
                try:
                    signature.bind(anchor=anchor, **{action_name: action})
                except TypeError:
                    continue
                return self._on_menu(anchor=anchor, **{action_name: action})
        if action == "settings":
            # Compatibility with the current bound app callback: invoke the
            # parent's Settings entry point, never duplicate its construction.
            direct = getattr(getattr(self._on_menu, "__self__", None), "show_settings", None)
            if callable(direct):
                return direct()
        try:
            if signature is not None:
                signature.bind(anchor)
            return self._on_menu(anchor)
        except TypeError:
            return self._on_menu()

    def _export_document(self):
        self._commit_active_field()
        if self._on_export is None:
            self._mostra_errore("Generazione Google Doc non disponibile.")
            return
        self._on_export(self._editor)

    def _open_exercise_menu(self, indice, anchor):
        if not self._ready_for_action():
            return None
        self._commit_active_field()
        callbacks = {
            "Su": lambda: self._wrap(
                lambda: self._editor.sposta(indice, -1), rebuild=True),
            "Giù": lambda: self._wrap(
                lambda: self._editor.sposta(indice, 1), rebuild=True),
            "Vai a…": lambda: self._vai_a(indice),
            "Gruppo": lambda: self._group_popup(indice),
            "Duplica": lambda: self._duplicate(indice),
            "Elimina": lambda: self._confirm_delete(indice),
        }
        return apri_menu(
            tuple((label, callbacks[label]) for label in exercise_context_actions()),
            anchor=anchor,
        )

    def _duplicate(self, indice):
        self._commit_active_field()
        try:
            self._open_index = self._editor.duplica(indice)
        except Exception as exc:
            self._mostra_errore(exc)
            return
        self._rebuild()

    def _button(self, **kwargs):
        """Build an editor-owned button at the active 44/52/60 preset."""
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", self._target_h)
        return Button(**kwargs)

    def _exercise_block(self, indice, esercizio):
        block = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(8))
        block.bind(minimum_height=block.setter("height"))
        profile = profile_for_window(Window)
        layout = editor_layout(profile)

        header = BoxLayout(size_hint_y=None, height=self._target_h, spacing=dp(6))
        toggle = self._button(text="▾" if indice == self._open_index else "▸",
                        size_hint=(None, None), width=self._target_h, height=self._target_h)
        toggle.bind(on_release=lambda *_: self._toggle_exercise(indice))
        titolo = Label(text=f"{indice + 1}. {esercizio.get('nome') or '(senza nome)'}",
                       halign="left", valign="middle", shorten=True, shorten_from="right")
        titolo.bind(width=lambda _, v, l=titolo: setattr(l, "text_size", (v, l.height)))
        video = self._button(text="Video/Frame", size_hint=(None, None),
                       width=max(dp(112), self._target_h * 2), height=self._target_h)
        if self._open_media is not None:
            video.bind(on_release=lambda _, i=indice: self._open_video(i))
        context = self._button(text="⋮", size_hint=(None, None),
                         width=self._target_h, height=self._target_h)
        context.bind(on_release=lambda button, i=indice: self._open_exercise_menu(i, button))
        header.add_widget(toggle)
        header.add_widget(titolo)
        header.add_widget(video)
        header.add_widget(context)
        block.add_widget(header)

        if indice != self._open_index:
            return block

        campo_h = dp(profile.tokens.dimensions["field_height"])
        griglia = GridLayout(cols=4, spacing=(dp(10), dp(6)), size_hint_y=None,
                             row_default_height=campo_h, row_force_default=True)

        def ricalcola_griglia(*_, g=griglia, b=block):
            largo_dp = max(b.width, 1) / profile.viewport.system_density
            per_riga = field_columns(profile_for_window(Window), largo_dp)
            g.cols = per_riga
            righe = math.ceil(len(CAMPI_BREVI) / per_riga)
            g.height = righe * campo_h + (righe - 1) * dp(6)
        block.bind(width=ricalcola_griglia)
        for chiave, etichetta in CAMPI_BREVI:
            cella = BoxLayout(orientation="vertical" if layout.labels_above else "horizontal", spacing=dp(4))
            etichetta_label = Label(text=etichetta, size_hint_x=1 if layout.labels_above else None,
                                    width=0 if layout.labels_above else dp(95),
                                    halign="left", valign="middle")
            etichetta_label.bind(
                width=lambda _, v, l=etichetta_label: setattr(l, "text_size", (v, campo_h)))
            cella.add_widget(etichetta_label)
            campo = TextInput(text=str(esercizio.get(chiave) or ""), multiline=False,
                              hint_text=etichetta,
                              **({} if not layout.labels_above else
                                 {"size_hint_y": None, "height": campo_h}))
            campo.bind(focus=self._field_handler(indice, chiave, campo))
            self._fields.append(campo)
            cella.add_widget(campo)
            griglia.add_widget(cella)
        block.add_widget(griglia)

        for chiave, etichetta in CAMPI_LUNGHI:
            box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
            box.bind(minimum_height=box.setter("height"))
            etichetta_label = Label(text=etichetta, size_hint_y=None, height=dp(20),
                                    halign="left", valign="middle")
            etichetta_label.bind(
                width=lambda _, v, l=etichetta_label: setattr(l, "text_size", (v, l.height)))
            box.add_widget(etichetta_label)
            campo = TextInput(text=str(esercizio.get(chiave) or ""), multiline=True,
                              hint_text=etichetta, size_hint_y=None, height=dp(90))
            campo.bind(focus=self._field_handler(indice, chiave, campo))
            self._fields.append(campo)
            box.add_widget(campo)
            block.add_widget(box)
        return block

    def _toggle_exercise(self, indice):
        if not self._ready_for_action():
            return
        self._commit_active_field()
        self._open_index = -1 if indice == self._open_index else indice
        self._rebuild()

    def _open_video(self, indice):
        if not self._ready_for_action():
            return
        self._commit_active_field()
        if self._open_media is not None:
            self._open_media(self._editor, indice)

    def _confirm_delete(self, indice):
        if not self._ready_for_action():
            return
        self._commit_active_field()
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Conferma eliminazione", content=content,
                      size_hint=(0.8, 0.3), auto_dismiss=False)
        nome = self._editor.esercizi[indice].get("nome") or f"esercizio {indice + 1}"
        content.add_widget(Label(text=f"Eliminare '{nome}'?"))
        actions = BoxLayout(size_hint_y=None, height=self._target_h, spacing=dp(8))
        cancel = self._button(text="Annulla")
        confirm = self._button(text="Elimina")
        cancel.bind(on_release=lambda *_: popup.dismiss())
        confirm.bind(on_release=lambda *_: (
            popup.dismiss(),
            self._wrap(lambda: self._editor.rimuovi(indice), rebuild=True)))
        actions.add_widget(cancel)
        actions.add_widget(confirm)
        content.add_widget(actions)
        popup.open()

    def _field_handler(self, indice, chiave, campo):
        def on_focus(instance, focused):
            if focused:
                return
            valore = campo.text
            corrente = self._editor.esercizi[indice].get(chiave) or ""
            if valore == corrente:
                return
            self._wrap(lambda: self._editor.aggiorna(indice, **{chiave: valore}))
        return on_focus

    def _commit_active_field(self):
        for campo in self._fields:
            if campo.focus:
                campo.focus = False
                return

    def richiedi_uscita(self, on_continue=None):
        if not self._ready_for_action():
            return
        self._commit_active_field()
        target = on_continue or self._on_back
        if not self._editor.sporco:
            target()
            return
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Modifiche non salvate", content=content,
                      size_hint=(0.85, 0.35), auto_dismiss=False)
        content.add_widget(Label(text="Vuoi salvare le modifiche prima di uscire?"))
        actions = BoxLayout(size_hint_y=None, height=self._target_h, spacing=dp(8))
        save = self._button(text="Salva")
        discard = self._button(text="Scarta")
        stay = self._button(text="Resta")
        save.bind(on_release=lambda *_: (
            popup.dismiss(), self.apri_salvataggio(chiudi=True, on_close=target)))
        discard.bind(on_release=lambda *_: (popup.dismiss(), self._editor.discard(), target()))
        stay.bind(on_release=lambda *_: popup.dismiss())
        for button in (save, discard, stay):
            actions.add_widget(button)
        content.add_widget(actions)
        popup.open()

    def apri_salvataggio(self, chiudi=False, on_close=None):
        if not self._ready_for_action():
            return
        self._commit_active_field()
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Salva scheda", content=content, size_hint=(0.8, 0.3),
                      auto_dismiss=True)
        locale = self._button(text="Salva in locale")
        drive = self._button(text="Salva su Drive")
        locale.bind(on_release=lambda *_: (popup.dismiss(), self._salva_locale(chiudi, on_close)))
        drive.bind(on_release=lambda *_: (popup.dismiss(), self._salva_drive(chiudi, on_close)))
        content.add_widget(locale)
        content.add_widget(drive)
        popup.open()

    def _salva_locale(self, chiudi, on_close):
        # On Android (local_store present) the mirror folder is fixed, so save
        # directly; on the PC a native dialog picks the destination file.
        if self._controller.local_store is not None:
            self._save(False, chiudi, on_close)
            return
        default = Path(self._editor.percorso_bundle).name

        def scelto(percorso):
            self._save(False, chiudi, on_close, destinazione=percorso)
        choose_save_file(scelto, default_name=default, title="Salva scheda con nome")

    def _salva_drive(self, chiudi, on_close):
        if self._editor.pubblicato_su_drive:
            self._save(True, chiudi, on_close)
            return
        nome = Path(self._editor.percorso_bundle).name
        try:
            remoto = self._controller.remoto_con_nome(nome)
        except Exception as exc:  # HomeUnavailableError e simili
            self._mostra_errore(exc)
            return
        if remoto is None:
            self._pubblica(chiudi, on_close, None)
            return
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Nome già in uso su Drive", content=content,
                      size_hint=(0.85, 0.4), auto_dismiss=False)
        popup.add_widget(Label(text=f"'{remoto.name}' esiste già su Drive. "
                                    "Vuoi sovrascriverlo?"))
        azioni = BoxLayout(size_hint_y=None, height=self._target_h, spacing=dp(8))
        sovrascrivi = self._button(text="Sovrascrivi")
        annulla = self._button(text="Annulla")
        sovrascrivi.bind(on_release=lambda *_: (popup.dismiss(), self._pubblica(chiudi, on_close, remoto)))
        annulla.bind(on_release=lambda *_: popup.dismiss())
        azioni.add_widget(sovrascrivi)
        azioni.add_widget(annulla)
        content.add_widget(azioni)
        popup.open()

    def _pubblica(self, chiudi, on_close, remoto):
        if self._saving:
            self._mostra_info("Salvataggio già in corso: attendi il termine.")
            return
        self._saving = True
        self._blocca(True)
        self._mostra_info("Pubblicazione su Drive in corso…")
        target = on_close or self._on_back

        def worker():
            try:
                self._controller.pubblica_in_drive(self._editor, remoto=remoto)
            except Exception as exc:
                Clock.schedule_once(lambda _, e=exc: esito(e, None), 0)
            else:
                # Clock always supplies ``dt``; accepting it prevents the UI
                # from remaining permanently blocked after a successful publish.
                Clock.schedule_once(lambda _dt: esito(None, None), 0)

        def esito(eccezione, _):
            self._saving = False
            self._blocca(False)
            if eccezione is not None:
                self._mostra_errore(
                    f"Pubblicazione su Drive non riuscita: {eccezione}. "
                    "Modifiche salvate in locale."
                )
                return
            self._refresh_status()
            self._mostra_info("Scheda pubblicata su Drive.")
            if chiudi:
                target()

        threading.Thread(target=worker, daemon=True).start()

    def _group_popup(self, indice):
        gruppi = self._editor.gruppi_esistenti()
        content = BoxLayout(orientation="vertical", spacing=4)
        popup = Popup(title="Gruppi esistenti", content=content, size_hint=(0.8, 0.6))
        for nome in gruppi:
            choice = self._button(text=nome)
            choice.bind(on_release=lambda _, value=nome: self._pick_group(indice, value, popup))
            content.add_widget(choice)
        if not gruppi:
            content.add_widget(Label(text="Nessun gruppo presente: scrivilo nel campo Gruppo."))
        popup.open()

    def _pick_group(self, indice, nome, popup):
        popup.dismiss()
        self._wrap(lambda: self._editor.aggiorna(indice, gruppo=nome), rebuild=True)

    def _numero_popup(self, titolo, prompt, minimo, massimo, confermato, iniziale=None):
        profile = profile_for_window(Window)
        riga = int(profile.touch_target)
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title=titolo, content=content, size_hint=(0.8, None),
                      height=dp(3 * riga + 64))
        etichetta = Label(text=f"{prompt} ({minimo}-{massimo})", halign="left",
                          valign="middle", size_hint_y=None, height=dp(riga))
        etichetta.bind(width=lambda _, v, l=etichetta: setattr(l, "text_size", (v, dp(riga))))
        content.add_widget(etichetta)
        campo = TextInput(text=str(iniziale if iniziale is not None else minimo),
                          multiline=False, input_filter="int", size_hint_y=None, height=dp(riga))
        content.add_widget(campo)
        bot = BoxLayout(size_hint_y=None, height=dp(riga), spacing=dp(8))
        ok = self._button(text="Ok")
        cancel = self._button(text="Annulla")

        def valida(*_):
            try:
                numero = int(campo.text)
            except (TypeError, ValueError):
                self._mostra_errore("Inserisci un numero valido.")
                return
            popup.dismiss()
            confermato(numero)

        ok.bind(on_release=valida)
        campo.bind(on_text_validate=valida)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        bot.add_widget(ok)
        bot.add_widget(cancel)
        content.add_widget(bot)
        popup.open()

    def _vai_a(self, indice):
        massimo = len(self._editor.esercizi)
        if massimo <= 1:
            self._mostra_info("Serve più di un esercizio per spostare.")
            return

        def conferma(numero):
            if not 1 <= numero <= massimo:
                self._mostra_errore(f"Posizione fuori intervallo (1-{massimo}).")
                return
            self._wrap(lambda: self._editor.sposta_alla(indice, numero - 1), rebuild=True)

        self._numero_popup(f"Sposta '{self._editor.esercizi[indice].get('nome') or indice + 1}'",
                           "Nuova posizione", 1, massimo, conferma, iniziale=indice + 1)

    def _posizione_inserimento(self, callback):
        massimo = len(self._editor.esercizi) + 1

        def conferma(numero):
            if not 1 <= numero <= massimo:
                self._mostra_errore(f"Posizione fuori intervallo (1-{massimo}).")
                return
            self._wrap(lambda: callback(numero - 1), rebuild=True)

        self._numero_popup("Punto di inserimento", "Inserisci alla posizione", 1, massimo,
                           conferma, iniziale=1)

    def _mode_popup(self, titolo, applica):
        content = BoxLayout(orientation="vertical", spacing=8)
        popup = Popup(title=titolo, content=content, size_hint=(0.8, 0.42))
        replace = self._button(text="Sostituisci tutti gli esercizi")
        merge = self._button(text="Aggiungi in fondo")
        posiziona = self._button(text="Inserisci in una posizione…")
        replace.bind(on_release=lambda *_: (popup.dismiss(), self._wrap(lambda: applica(True, None), rebuild=True)))
        merge.bind(on_release=lambda *_: (popup.dismiss(), self._wrap(lambda: applica(False, None), rebuild=True)))

        def apri_posizione(*_):
            popup.dismiss()
            self._posizione_inserimento(lambda p: applica(False, p))

        posiziona.bind(on_release=apri_posizione)
        content.add_widget(replace)
        content.add_widget(merge)
        content.add_widget(posiziona)
        popup.open()

    def _import_csv(self):
        """Choose the CSV source: a local file or one already in the Drive folder."""
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Importa CSV", content=content, size_hint=(0.8, 0.32))
        locale = self._button(text="Da file locale")
        drive = self._button(text="Dalla cartella Drive")
        locale.bind(on_release=lambda *_: (popup.dismiss(), self._import_csv_locale()))
        drive.bind(on_release=lambda *_: (popup.dismiss(), self._csv_da_drive()))
        content.add_widget(locale)
        content.add_widget(drive)
        popup.open()

    def _import_csv_locale(self):
        def on_result(percorso):
            if percorso:
                self._procedi_import_csv(percorso, locale=True)
        choose_file(on_result, title="Importa CSV manifest", parent=self,
                    patterns=[("CSV", "*.csv")])

    def _csv_da_drive(self):
        """Let the user pick a CSV listed in the configured Drive folder."""
        try:
            csvs = self._controller.list_csv()
        except Exception as exc:
            self._mostra_errore(exc)
            return
        content = BoxLayout(orientation="vertical", spacing=4)
        popup = Popup(title="Importa CSV da Drive", content=content, size_hint=(0.8, 0.6))
        for remote in csvs:
            choice = self._button(text=remote.name)
            choice.bind(on_release=lambda _, item=remote: (
                popup.dismiss(), self._csv_da_drive_download(item)))
            content.add_widget(choice)
        if not csvs:
            content.add_widget(Label(text="Nessun CSV trovato su Drive."))
        popup.open()

    def _csv_da_drive_download(self, remote):
        self._mostra_info("Scarico il CSV da Drive…")

        def fine(percorso, errore):
            self._attendo_csv = False
            if errore is not None:
                self._mostra_errore(errore)
            else:
                self._procedi_import_csv(percorso)

        def lavoro():
            try:
                percorso = self._controller.download_csv(remote)
            except Exception as exc:
                Clock.schedule_once(lambda _, e=exc: fine(None, e), 0)
            else:
                Clock.schedule_once(lambda _, p=percorso: fine(p, None), 0)

        if getattr(self, "_attendo_csv", False):
            return
        self._attendo_csv = True
        threading.Thread(target=lavoro, daemon=True).start()

    def _procedi_import_csv(self, percorso, *, locale=False):
        def importa(sostituisci, posizione):
            if locale:
                return self._controller.importa_csv_locale(
                    self._editor, percorso, sostituisci=sostituisci, posizione=posizione)
            return self._editor.importa_csv(
                percorso, sostituisci=sostituisci, posizione=posizione)

        self._mode_popup(
            f"Importa {Path(percorso).name}",
            importa)

    def _import_scheda(self):
        try:
            remote_id = getattr(self._remote, "id", None)
            schede = [r for r in self._controller.refresh() if r.id != remote_id]
        except Exception as exc:  # HomeUnavailableError e simili
            self._mostra_errore(exc)
            return
        content = BoxLayout(orientation="vertical", spacing=4)
        popup = Popup(title="Importa da un'altra scheda", content=content, size_hint=(0.8, 0.6))
        for remote in schede:
            choice = self._button(text=remote.name)
            choice.bind(on_release=lambda _, item=remote: (popup.dismiss(), self._scheda_mode(item)))
            content.add_widget(choice)
        if not schede:
            content.add_widget(Label(text="Ness'altra scheda trovata su Drive."))
        popup.open()

    def _scheda_mode(self, remote):
        self._mostra_info("Carico gli esercizi della scheda…")

        def fine(esercizi, errore):
            self._attendo_import = False
            if errore is not None:
                self._mostra_errore(errore)
            else:
                self._popup_selezione_import(remote, esercizi)

        def lavoro():
            try:
                esercizi = self._controller.open_for_workout(remote)
            except Exception as exc:
                Clock.schedule_once(lambda _, e=exc: fine(None, e), 0)
            else:
                Clock.schedule_once(lambda _, es=esercizi: fine(es, None), 0)

        if getattr(self, "_attendo_import", False):
            return
        self._attendo_import = True
        threading.Thread(target=lavoro, daemon=True).start()

    def _popup_selezione_import(self, remote, esercizi):
        scroll = ScrollView()
        interno = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        interno.bind(minimum_height=interno.setter("height"))
        caselle: list[tuple[int, CheckBox]] = []
        tutto = {"attivo": True}
        toggle = self._button(text="Deseleziona tutti")

        def commuta(*_):
            tutto["attivo"] = not tutto["attivo"]
            for _, casella in caselle:
                casella.active = tutto["attivo"]
            toggle.text = ("Deseleziona tutti" if tutto["attivo"] else "Seleziona tutti")

        toggle.bind(on_release=commuta)
        interno.add_widget(toggle)
        for indice, esercizio in enumerate(esercizi):
            riga = BoxLayout(size_hint_y=None, height=self._target_h, spacing=dp(8))
            casella = CheckBox(active=True)
            caselle.append((indice, casella))
            etichetta = Label(text=f"{indice + 1}. {esercizio.get('nome') or '(senza nome)'}",
                              halign="left", valign="middle")
            etichetta.bind(width=lambda _, v, l=etichetta: setattr(l, "text_size", (v, None)))
            riga.add_widget(casella)
            riga.add_widget(etichetta)
            interno.add_widget(riga)
        avanti = self._button(text="Avanti…")

        def conferma(*_):
            indici = {i for i, casella in caselle if casella.active}
            popup.dismiss()
            if not indici:
                self._mostra_errore("Seleziona almeno un esercizio da importare.")
                return
            self._mode_popup(
                f"Importa {len(indici)} esercizi da {remote.name}",
                lambda sostituisci, posizione: self._controller.import_remote_into(
                    self._editor, remote, sostituisci=sostituisci, posizione=posizione,
                    indici=indici))

        avanti.bind(on_release=conferma)
        interno.add_widget(avanti)
        scroll.add_widget(interno)
        popup = Popup(title="Scegli gli esercizi", content=scroll, size_hint=(0.85, 0.8),
                      auto_dismiss=False)
        popup.open()

    def _blocca(self, value):
        for widget in self.walk(restrict=True):
            if isinstance(widget, (Button, TextInput, CheckBox)):
                widget.disabled = value

    def _save(self, sincronizza=True, chiudi=False, on_close=None, destinazione=None):
        self._commit_active_field()
        target = on_close or self._on_back
        if self._saving:
            self._mostra_info("Salvataggio già in corso: attendi il termine.")
            return
        self._saving = True
        self._blocca(True)
        self._mostra_info("Salvataggio su Drive in corso…" if sincronizza
                          else "Salvataggio locale in corso…")

        def worker():
            try:
                risultato = self._editor.salva(sincronizza=sincronizza, destinazione=destinazione)
            except Exception as exc:
                Clock.schedule_once(lambda _, e=exc: esito(e, None), 0)
            else:
                Clock.schedule_once(lambda _, r=risultato: esito(None, r), 0)

        def esito(eccezione, risultato):
            self._saving = False
            self._blocca(False)
            copia = getattr(self._editor, "ultima_copia_locale", None)
            se_copia = f" Copia in: {copia}." if copia else ""
            if eccezione is not None:
                if isinstance(eccezione, EditorValidationError):
                    messaggio = str(eccezione)
                else:
                    messaggio = ((f"Salvataggio locale ok, Drive non raggiungibile: {eccezione}."
                                  + se_copia)
                                 if sincronizza else f"Salvataggio locale fallito: {eccezione}")
                self._refresh_status()
                self._mostra_errore(messaggio)
                return
            if not sincronizza:
                self._refresh_status()
                self._mostra_info("Scheda salvata in locale (Drive non aggiornato)." + se_copia)
                if chiudi:
                    target()
                return
            if isinstance(risultato, SyncConflict):
                from .conflict_dialog import apri_dialogo_conflitto
                apri_dialogo_conflitto(self._controller, risultato, self._esito_conflitto,
                                       local_path=self._editor.percorso_bundle)
                return
            if self._editor.sporco:
                self._mostra_errore("Salvato solo in locale: upload su Drive non riuscito."
                                    + se_copia)
            else:
                self._refresh_status()
                self._mostra_info("Salvato su Drive.")
                if chiudi:
                    target()

        threading.Thread(target=worker, daemon=True).start()

    def _esito_conflitto(self, choice, esito):
        if isinstance(esito, Exception):
            self._mostra_errore(esito)
            return
        self._editor.conferma_salvataggio()
        if choice == "locale":
            self._refresh_status()
            self._mostra_info("Versione locale inviata a Drive.")
        elif choice == "remota":
            self._on_conflict_exit("Ricaricata la versione remota: modifiche locali scartate.")
        else:
            self._on_conflict_exit("Versione locale duplicata su Drive; originale riallineato.")

    def _wrap(self, operation, rebuild=False):
        if not self._ready_for_action():
            return
        self._commit_active_field()
        try:
            operation()
        except Exception as exc:
            self._mostra_errore(exc)
            return
        if rebuild:
            self._rebuild()
        else:
            self._refresh_status()

    def _on_key_down(self, _window, key, _scancode, _codepoint, modifiers):
        if self._saving:
            return True
        if key == 27:
            # Android's physical Back follows the application close contract;
            # ``PyTrainerApp._on_request_close`` still asks Save/Discard/Stay
            # when this editor is dirty. Desktop Escape remains in-view Back.
            import sys
            if sys.platform == "android":
                return False
            self.richiedi_uscita()
            return True
        if "ctrl" not in modifiers:
            return False
        if key == 115:  # Ctrl+S
            self.apri_salvataggio()
        elif key == 122:  # Ctrl+Z / Ctrl+Shift+Z
            self._wrap(self._editor.redo if "shift" in modifiers else self._editor.undo,
                       rebuild=True)
        elif key == 121:  # Ctrl+Y
            self._wrap(self._editor.redo, rebuild=True)
        else:
            return False
        return True

    def _mostra_errore(self, exc):
        from .controller import HomeUnavailableError
        if isinstance(exc, EditorValidationError):
            messaggio = str(exc)
        elif isinstance(exc, HomeUnavailableError):
            messaggio = str(exc)
        else:
            messaggio = str(exc) if isinstance(exc, str) else f"Errore imprevisto: {exc}"
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Errore", content=content, size_hint=(0.82, None),
                      height=dp(160) + self._target_h, auto_dismiss=False)
        content.add_widget(Label(text=messaggio, halign="center", valign="middle"))
        ok = self._button(text="OK")
        ok.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(ok)
        popup.open()
        return popup

    def _mostra_info(self, messaggio):
        return mostra_snackbar(self, str(messaggio))

    def _ready_for_action(self):
        if not self._saving:
            return True
        self._mostra_info("Operazione non disponibile durante il salvataggio.")
        return False

    def dispose(self):
        """Release the process-wide keyboard binding when leaving the editor."""
        if self._disposed:
            return
        Window.unbind(on_key_down=self._on_key_down)
        self._disposed = True

    def _refresh_status(self):
        parti = []
        duplicati = self._editor.duplicati_slug()
        if duplicati:
            collisioni = "; ".join(
                f"{slug}: esercizi {', '.join(str(i + 1) for i in indici)}"
                for slug, indici in sorted(duplicati.items())
            )
            parti.append(f"ATTENZIONE slug duplicati ({collisioni})")
        if self._editor.sporco:
            parti.append("* modifiche non salvate")
        elif getattr(self._editor, "non_sincronizzato", False):
            parti.append("o salvata in locale: Drive da sincronizzare")
        else:
            parti.append("nessuna modifica pending")
        avvertenza = getattr(self._controller, "avvertenza", None)
        if avvertenza:
            parti.insert(0, avvertenza)
        self.status.text = " - ".join(parti)
