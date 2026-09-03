"""Kivy screen for editing one opened scheda (ticket 06).

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
All domain behavior lives in ``kivy_app.editor.SchedaEditorController``;
this module only renders and forwards events.
"""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core.drive_sync import SyncConflict

from .editor import EditorValidationError
from .file_picker import choose_file


CAMPI_BREVI = (("nome", "Nome"), ("gruppo", "Gruppo"),
               ("ripetizioni", "Ripetizioni"), ("recupero", "Recupero"))
CAMPI_LUNGHI = (("spiegazione", "Spiegazione"), ("note", "Note"))


class EditorScreen(BoxLayout):
    def __init__(self, controller, editor, remote, on_back, open_media=None, on_export=None,
                 on_conflict_exit=None):
        super().__init__(orientation="vertical", padding=10, spacing=6)
        self._controller = controller
        self._editor = editor
        self._remote = remote
        self._on_back = on_back
        self._open_media = open_media
        self._on_export = on_export
        self._on_conflict_exit = on_conflict_exit or (lambda message: self._on_back())

        self.header = BoxLayout(size_hint_y=None, height=44, spacing=8)
        back = Button(text="< Indietro", size_hint_x=None, width=120)
        back.bind(on_release=lambda *_: self._on_back())
        self.status = Label(text="", halign="left", valign="middle",
                            shorten=True, shorten_from="right")
        save = Button(text="Salva", size_hint_x=None, width=110)
        save.bind(on_release=lambda *_: self._save())
        self.header.add_widget(back)
        self.header.add_widget(self.status)
        self.header.add_widget(save)
        self.add_widget(self.header)

        self.rows = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        self.rows.bind(minimum_height=self.rows.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.rows)
        self.add_widget(scroll)

        tools = BoxLayout(size_hint_y=None, height=48, spacing=8)
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
            export = Button(text="Genera Google Doc", size_hint_x=None, width=170)
            export.bind(on_release=lambda *_: self._on_export(self._editor))
            tools.add_widget(export)
        self.add_widget(tools)

        self._rebuild()

    def _rebuild(self):
        self.rows.clear_widgets()
        for indice, esercizio in enumerate(self._editor.esercizi):
            self.rows.add_widget(self._exercise_block(indice, esercizio))
        self._refresh_status()

    def _exercise_block(self, indice, esercizio):
        block = BoxLayout(orientation="vertical", size_hint_y=None, spacing=2)
        title = BoxLayout(size_hint_y=None, height=34, spacing=6)
        title.add_widget(Label(text=f"{indice + 1}. {esercizio.get('nome') or '(senza nome)'}",
                               size_hint_x=None, width=220, halign="left",
                               text_size=(220, None)))
        spacer = Label(text="")
        up = Button(text="Su", size_hint_x=None, width=60)
        up.bind(on_release=lambda *_: self._wrap(lambda: self._editor.sposta(indice, -1), rebuild=True))
        down = Button(text="Giù", size_hint_x=None, width=60)
        down.bind(on_release=lambda *_: self._wrap(lambda: self._editor.sposta(indice, 1), rebuild=True))
        groups = Button(text="Gruppi", size_hint_x=None, width=90)
        groups.bind(on_release=lambda _, i=indice: self._group_popup(i))
        video = Button(text="Video&Frame", size_hint_x=None, width=120)
        if self._open_media is not None:
            video.bind(on_release=lambda _, i=indice: self._open_media(self._editor, i))
        delete = Button(text="Elimina", size_hint_x=None, width=90)
        delete.bind(on_release=lambda *_: self._wrap(lambda: self._editor.rimuovi(indice), rebuild=True))
        title.add_widget(spacer)
        title.add_widget(up)
        title.add_widget(down)
        title.add_widget(groups)
        title.add_widget(video)
        title.add_widget(delete)
        block.add_widget(title)

        for row_key in (CAMPI_BREVI, CAMPI_LUNGHI):
            line = BoxLayout(size_hint_y=None,
                             height=90 if row_key is CAMPI_LUNGHI else 40, spacing=4)
            for chiave, etichetta in row_key:
                line.add_widget(Label(text=etichetta, size_hint_x=None, width=90,
                                      halign="left"))
                campo = TextInput(
                    text=str(esercizio.get(chiave) or ""),
                    multiline=row_key is CAMPI_LUNGHI, size_hint_x=1,
                    hint_text=etichetta,
                )
                campo.bind(focus=self._field_handler(indice, chiave, campo))
                line.add_widget(campo)
            block.add_widget(line)
        return block

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

    def _mode_popup(self, titolo, applica):
        content = BoxLayout(orientation="vertical", spacing=8)
        popup = Popup(title=titolo, content=content, size_hint=(0.8, 0.35))
        replace = Button(text="Sostituisci tutti gli esercizi")
        merge = Button(text="Aggiungi in fondo")
        replace.bind(on_release=lambda *_: (popup.dismiss(), self._wrap(lambda: applica(True), rebuild=True)))
        merge.bind(on_release=lambda *_: (popup.dismiss(), self._wrap(lambda: applica(False), rebuild=True)))
        content.add_widget(replace)
        content.add_widget(merge)
        popup.open()

    def _import_csv(self):
        def on_result(percorso):
            if not percorso:
                return
            self._mode_popup(f"Importa {percorso}",
                             lambda sostituisci: self._editor.importa_csv(percorso, sostituisci=sostituisci))
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
        self._mode_popup(f"Importa {remote.name}",
                         lambda sostituisci: self._controller.import_remote_into(
                             self._editor, remote, sostituisci=sostituisci))

    def _save(self):
        try:
            risultato = self._editor.salva()
        except EditorValidationError as exc:
            self.status.text = str(exc)
            return
        except Exception as exc:
            self.status.text = f"Salvataggio locale ok, Drive non raggiungibile: {exc}"
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
        parti.append("* modifiche non salvate" if self._editor.sporco else "nessuna modifica pending")
        self.status.text = " - ".join(parti)
