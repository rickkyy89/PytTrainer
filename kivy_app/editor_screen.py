"""Kivy screen for editing one opened scheda (ticket 06).

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
All domain behavior lives in ``kivy_app.editor.SchedaEditorController``;
this module only renders and forwards events.
"""

from __future__ import annotations

import math

from kivy.metrics import dp
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core.drive_sync import SyncConflict

from .editor import EditorValidationError
from .file_picker import choose_file
from .editor_layout import editor_layout, field_columns
from .material import profile_for_window


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

        self.header = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        if self._on_menu is not None:
            menu = Button(text="Menu", size_hint_x=None, width=dp(82))
            menu.bind(on_release=lambda *_: self.richiedi_uscita(self._on_menu))
            self.header.add_widget(menu)
        back = Button(text="< Indietro", size_hint_x=None, width=dp(120))
        back.bind(on_release=lambda *_: self.richiedi_uscita())
        self.status = Label(text="", halign="left", valign="middle",
                            shorten=True, shorten_from="right")
        self.status.bind(
            width=lambda _, v: setattr(self.status, "text_size", (v, self.status.height)))
        self.header.add_widget(back)
        self.header.add_widget(self.status)
        self.add_widget(self.header)
        Window.bind(on_key_down=self._on_key_down)

        self.rows = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self._scroll = ScrollView()
        self._scroll.add_widget(self.rows)
        self.add_widget(self._scroll)

        tools = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        add = Button(text="Aggiungi esercizio")
        add.bind(on_release=lambda *_: self._wrap(self._editor.aggiungi, rebuild=True))
        csv = Button(text="Importa CSV")
        csv.bind(on_release=lambda *_: self._import_csv())
        scheda = Button(text="Importa da scheda")
        scheda.bind(on_release=lambda *_: self._import_scheda())
        tools.add_widget(add)
        tools.add_widget(csv)
        tools.add_widget(scheda)
        if self._on_export is not None:
            export = Button(text="Genera Google Doc", size_hint_x=None, width=dp(170))
            export.bind(on_release=lambda *_: self._on_export(self._editor))
            tools.add_widget(export)
        self.add_widget(tools)

        # Undo, redo and save stay reachable while the form scrolls.
        action_bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        action_profile = profile_for_window(Window)
        undo_bar = Button(text="Annulla", size_hint_x=None, width=dp(action_profile.touch_target * 2))
        undo_bar.bind(on_release=lambda *_: self._wrap(self._editor.undo, rebuild=True))
        redo_bar = Button(text="Ripeti", size_hint_x=None, width=dp(action_profile.touch_target * 2))
        redo_bar.bind(on_release=lambda *_: self._wrap(self._editor.redo, rebuild=True))
        save_bar = Button(text="Salva", size_hint_x=None, width=dp(action_profile.touch_target * 2))
        save_bar.bind(on_release=lambda *_: self.apri_salvataggio())
        for button in (undo_bar, redo_bar, save_bar):
            action_bar.add_widget(button)
        self.add_widget(action_bar)

        self._rebuild()

    @property
    def modifiche_non_salvate(self):
        return self._editor.sporco

    def _rebuild(self):
        self.rows.clear_widgets()
        self._fields.clear()
        for indice, esercizio in enumerate(self._editor.esercizi):
            self.rows.add_widget(self._exercise_block(indice, esercizio))
        self._refresh_status()

    def _exercise_block(self, indice, esercizio):
        block = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(8))
        block.bind(minimum_height=block.setter("height"))
        profile = profile_for_window(Window)
        layout = editor_layout(profile)

        header = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        titolo = Label(text=f"{indice + 1}. {esercizio.get('nome') or '(senza nome)'}",
                       halign="left", valign="middle", shorten=True, shorten_from="right")
        titolo.bind(width=lambda _, v, l=titolo: setattr(l, "text_size", (v, l.height)))
        toggle = Button(text="Chiudi" if indice == self._open_index else "Apri",
                        size_hint_x=None, width=dp(70))
        toggle.bind(on_release=lambda *_: self._toggle_exercise(indice))
        up = Button(text="Su", size_hint_x=None, width=dp(60))
        up.bind(on_release=lambda *_: self._wrap(lambda: self._editor.sposta(indice, -1), rebuild=True))
        down = Button(text="Giù", size_hint_x=None, width=dp(60))
        down.bind(on_release=lambda *_: self._wrap(lambda: self._editor.sposta(indice, 1), rebuild=True))
        goto = Button(text="Vai a…", size_hint_x=None, width=dp(80))
        goto.bind(on_release=lambda _, i=indice: self._vai_a(i))
        groups = Button(text="Gruppi", size_hint_x=None, width=dp(90))
        groups.bind(on_release=lambda _, i=indice: self._group_popup(i))
        video = Button(text="Video&Frame", size_hint_x=None, width=dp(120))
        if self._open_media is not None:
            video.bind(on_release=lambda _, i=indice: self._open_media(self._editor, i))
        delete = Button(text="Elimina", size_hint_x=None, width=dp(90))
        delete.bind(on_release=lambda _, i=indice: self._confirm_delete(i))
        header.add_widget(titolo)
        header.add_widget(toggle)
        header.add_widget(up)
        header.add_widget(down)
        header.add_widget(goto)
        header.add_widget(groups)
        header.add_widget(video)
        header.add_widget(delete)
        block.add_widget(header)

        if indice != self._open_index:
            return block

        campo_h = dp(profile.tokens.dimensions["field_height"])
        griglia = GridLayout(cols=4, spacing=(dp(10), dp(6)), size_hint_y=None,
                             row_default_height=campo_h, row_force_default=True)

        def ricalcola_griglia(*_, g=griglia, b=block):
            largo_dp = max(b.width, 1) / profile.viewport.system_density
            per_riga = field_columns(profile, largo_dp)
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
        self._open_index = -1 if indice == self._open_index else indice
        self._rebuild()

    def _confirm_delete(self, indice):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Conferma eliminazione", content=content,
                      size_hint=(0.8, 0.3), auto_dismiss=False)
        nome = self._editor.esercizi[indice].get("nome") or f"esercizio {indice + 1}"
        content.add_widget(Label(text=f"Eliminare '{nome}'?"))
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel = Button(text="Annulla")
        confirm = Button(text="Elimina")
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
        self._commit_active_field()
        target = on_continue or self._on_back
        if not self._editor.sporco:
            target()
            return
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Modifiche non salvate", content=content,
                      size_hint=(0.85, 0.35), auto_dismiss=False)
        content.add_widget(Label(text="Vuoi salvare le modifiche prima di uscire?"))
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        save = Button(text="Salva")
        discard = Button(text="Scarta")
        stay = Button(text="Resta")
        save.bind(on_release=lambda *_: (
            popup.dismiss(), self.apri_salvataggio(chiudi=True, on_close=target)))
        discard.bind(on_release=lambda *_: (popup.dismiss(), self._editor.discard(), target()))
        stay.bind(on_release=lambda *_: popup.dismiss())
        for button in (save, discard, stay):
            actions.add_widget(button)
        content.add_widget(actions)
        popup.open()

    def apri_salvataggio(self, chiudi=False, on_close=None):
        self._commit_active_field()
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Salva scheda", content=content, size_hint=(0.8, 0.3),
                      auto_dismiss=True)
        locale = Button(text="Salva in locale")
        drive = Button(text="Salva su Drive")
        locale.bind(on_release=lambda *_: (popup.dismiss(), self._save(False, chiudi, on_close)))
        drive.bind(on_release=lambda *_: (popup.dismiss(), self._save(True, chiudi, on_close)))
        content.add_widget(locale)
        content.add_widget(drive)
        popup.open()

    def _group_popup(self, indice):
        gruppi = self._editor.gruppi_esistenti()
        content = BoxLayout(orientation="vertical", spacing=4)
        popup = Popup(title="Gruppi esistenti", content=content, size_hint=(0.8, 0.6))
        for nome in gruppi:
            choice = Button(text=nome, size_hint_y=None, height=44)
            choice.bind(on_release=lambda _, value=nome: self._pick_group(indice, value, popup))
            content.add_widget(choice)
        if not gruppi:
            content.add_widget(Label(text="Nessun gruppo presente: scrivilo nel campo Gruppo."))
        popup.open()

    def _pick_group(self, indice, nome, popup):
        popup.dismiss()
        self._wrap(lambda: self._editor.aggiorna(indice, gruppo=nome), rebuild=True)

    def _numero_popup(self, titolo, prompt, minimo, massimo, confermato, iniziale=None):
        content = BoxLayout(orientation="vertical", spacing=8)
        popup = Popup(title=titolo, content=content, size_hint=(0.8, 0.35))
        content.add_widget(Label(text=f"{prompt} ({minimo}-{massimo})", halign="left",
                                 size_hint_y=None, height=30, text_size=(None, 30)))
        campo = TextInput(text=str(iniziale if iniziale is not None else minimo),
                          multiline=False, input_filter="int", size_hint_y=None, height=44)
        content.add_widget(campo)
        bot = BoxLayout(size_hint_y=None, height=44, spacing=8)
        ok = Button(text="Ok")
        cancel = Button(text="Annulla")

        def valida(*_):
            try:
                numero = int(campo.text)
            except (TypeError, ValueError):
                self.status.text = "Inserisci un numero valido."
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
            self.status.text = "Serve piu' di un esercizio per spostare."
            return

        def conferma(numero):
            if not 1 <= numero <= massimo:
                self.status.text = f"Posizione fuori intervallo (1-{massimo})."
                return
            self._wrap(lambda: self._editor.sposta_alla(indice, numero - 1), rebuild=True)

        self._numero_popup(f"Sposta '{self._editor.esercizi[indice].get('nome') or indice + 1}'",
                           "Nuova posizione", 1, massimo, conferma, iniziale=indice + 1)

    def _posizione_inserimento(self, callback):
        massimo = len(self._editor.esercizi) + 1

        def conferma(numero):
            if not 1 <= numero <= massimo:
                self.status.text = f"Posizione fuori intervallo (1-{massimo})."
                return
            self._wrap(lambda: callback(numero - 1), rebuild=True)

        self._numero_popup("Punto di inserimento", "Inserisci alla posizione", 1, massimo,
                           conferma, iniziale=1)

    def _mode_popup(self, titolo, applica):
        content = BoxLayout(orientation="vertical", spacing=8)
        popup = Popup(title=titolo, content=content, size_hint=(0.8, 0.42))
        replace = Button(text="Sostituisci tutti gli esercizi")
        merge = Button(text="Aggiungi in fondo")
        posiziona = Button(text="Inserisci in una posizione…")
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
        def on_result(percorso):
            if not percorso:
                return
            self._mode_popup(
                f"Importa {percorso}",
                lambda sostituisci, posizione: self._editor.importa_csv(
                    percorso, sostituisci=sostituisci, posizione=posizione))
        choose_file(on_result, title="Importa CSV manifest", parent=self,
                    patterns=[("CSV", "*.csv")])

    def _import_scheda(self):
        try:
            schede = [r for r in self._controller.refresh() if r.id != self._remote.id]
        except Exception as exc:  # HomeUnavailableError e simili
            self.status.text = str(exc)
            return
        content = BoxLayout(orientation="vertical", spacing=4)
        popup = Popup(title="Importa da un'altra scheda", content=content, size_hint=(0.8, 0.6))
        for remote in schede:
            choice = Button(text=remote.name, size_hint_y=None, height=44)
            choice.bind(on_release=lambda _, item=remote: (popup.dismiss(), self._scheda_mode(item)))
            content.add_widget(choice)
        if not schede:
            content.add_widget(Label(text="Ness'altra scheda trovata su Drive."))
        popup.open()

    def _scheda_mode(self, remote):
        self._mode_popup(
            f"Importa {remote.name}",
            lambda sostituisci, posizione: self._controller.import_remote_into(
                self._editor, remote, sostituisci=sostituisci, posizione=posizione))

    def _save(self, sincronizza=True, chiudi=False, on_close=None):
        self._commit_active_field()
        target = on_close or self._on_back
        try:
            risultato = self._editor.salva(sincronizza=sincronizza)
        except EditorValidationError as exc:
            self.status.text = str(exc)
            return
        except Exception as exc:
            self.status.text = (f"Salvataggio locale ok, Drive non raggiungibile: {exc}"
                                if sincronizza else f"Salvataggio locale fallito: {exc}")
            self._refresh_status()
            return
        if not sincronizza:
            self.status.text = "Scheda salvata in locale (Drive non aggiornato)."
            if chiudi:
                target()
            return
        if isinstance(risultato, SyncConflict):
            from .conflict_dialog import apri_dialogo_conflitto
            apri_dialogo_conflitto(self._controller, risultato, self._esito_conflitto,
                                   local_path=self._editor.percorso_bundle)
            return
        if self._editor.sporco:
            self.status.text = "Salvato solo in locale: upload su Drive non riuscito."
        else:
            self.status.text = "Salvato su Drive."
            if chiudi:
                target()

    def _esito_conflitto(self, choice, esito):
        if isinstance(esito, Exception):
            self.status.text = str(esito)
            return
        self._editor.conferma_salvataggio()
        if choice == "locale":
            self.status.text = "Versione locale inviata a Drive."
        elif choice == "remota":
            self._on_conflict_exit("Ricaricata la versione remota: modifiche locali scartate.")
        else:
            self._on_conflict_exit("Versione locale duplicata su Drive; originale riallineato.")

    def _wrap(self, operation, rebuild=False):
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
        if key == 27:
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
            self.status.text = str(exc)
        elif isinstance(exc, HomeUnavailableError):
            self.status.text = str(exc)
        else:
            self.status.text = f"Errore imprevisto: {exc}"

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
        self.status.text = " - ".join(parti)
