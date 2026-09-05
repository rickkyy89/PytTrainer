"""Kivy screen driving the Google Doc generation (ticket 08).

Shows the confirmation summary (ready/total), runs generation on a worker
thread while polling the checkpoint state for a live progress label, then
presents the final document URL with Open/Share actions and the regenerated
document warning when the previous state pointed to a deleted document.

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
"""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from .export import DocExportError
from .launcher import apri_url, condividi_url


class ExportScreen(BoxLayout):
    def __init__(self, export, on_back, on_menu=None):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8))
        self._export = export
        self._on_back = on_back
        self._on_menu = on_menu
        self._worker: threading.Thread | None = None
        self._url: str | None = None
        self._poll = None

        header = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        if self._on_menu is not None:
            self._menu = Button(text="Menu", size_hint_x=None, width=dp(82))
            self._menu.bind(on_release=lambda *_: self._on_menu())
            header.add_widget(self._menu)
        else:
            self._menu = None
        self._back = Button(text="< Editor", size_hint_x=None, width=dp(120))
        self._back.bind(on_release=lambda *_: self._exit())
        title = Label(text="Generazione Google Doc")
        header.add_widget(self._back)
        header.add_widget(title)
        self.add_widget(header)

        riepilogo = self._export.riepilogo()
        self.info = Label(
            text=(f"Titolo: {riepilogo.titolo}\n"
                  f"Esercizi pronti (frame START+FINISH): {riepilogo.pronti}/{riepilogo.totali}\n"
                  "La generazione crea un Google Doc A4 e sincronizza lo stato sul bundle."),
            halign="left", valign="top", size_hint_y=None, height=dp(110),
        )
        self.info.bind(width=lambda _, v: setattr(self.info, "text_size", (v, None)))
        self.info.bind(texture_size=lambda l, ts: setattr(l, "height", max(ts[1], dp(110))))
        self.add_widget(self.info)

        self.progress = Label(text="Premi Avvia per iniziare.", size_hint_y=None,
                              height=dp(32), halign="left", valign="top")
        self.progress.bind(
            width=lambda _, v: setattr(self.progress, "text_size", (v, None)))
        self.progress.bind(texture_size=lambda l, ts: setattr(l, "height", max(ts[1], dp(32))))
        self.add_widget(self.progress)

        self.actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.start_button = Button(text="Avvia")
        self.start_button.bind(on_release=lambda *_: self._start())
        self.actions.add_widget(self.start_button)
        self.add_widget(self.actions)

    def _start(self):
        if self._worker is not None:
            return
        self._url = None
        self.start_button.disabled = True
        self._back.disabled = True  # niente editor (e niente Salva) durante il worker
        if self._menu is not None:
            self._menu.disabled = True
        self.progress.text = "0% — avvio…"
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()
        self._poll = Clock.schedule_interval(self._tick, 0.5)

    def _run_worker(self):
        try:
            risultato = self._export.genera()
            Clock.schedule_once(lambda *_: self._done(risultato), 0)
        except Exception as exc:
            testo = str(exc) if isinstance(exc, DocExportError) else f"Errore: {exc}"
            Clock.schedule_once(lambda _, t=testo: self._failed(t), 0)

    def _tick(self, *_):
        inseriti, totale = self._export.progresso()
        percentuale = int(100 * inseriti / totale) if totale else 0
        self.progress.text = f"{percentuale}% — {inseriti}/{totale} esercizi"

    def _done(self, risultato):
        self._stop_polling()
        self._url = risultato.get("url")
        parti = [f"Documento generato: {len(risultato.get('esercizi_inseriti', []))} esercizi inseriti."]
        if risultato.get("documento_rigenerato"):
            parti.append("ATTENZIONE: il documento precedente era stato cancellato, "
                         "creato uno nuovo con URL diverso.")
        salvataggio = risultato.get("salvataggio")
        from core.drive_sync import SyncConflict, UploadResult
        if isinstance(salvataggio, SyncConflict):
            parti.append("Stato salvato nel bundle locale, CONFLITTO su Drive "
                         "(risoluzione in arrivo col ticket 10).")
        elif isinstance(salvataggio, UploadResult):
            parti.append("Stato sincronizzato su Drive.")
        self.progress.text = "\n".join(parti)
        self._build_result_actions()

    def _failed(self, testo):
        self._stop_polling()
        self.progress.text = testo
        self.start_button.disabled = False

    def _build_result_actions(self):
        self.actions.clear_widgets()
        if self._url:
            open_btn = Button(text="Apri documento")
            open_btn.bind(on_release=lambda *_: apri_url(self._url))
            share_btn = Button(text="Condividi")
            share_btn.bind(on_release=lambda *_: condividi_url(self._url, "Scheda d'allenamento"))
            retry = Button(text="Rigenera/riprendi", size_hint_x=None, width=160)
            retry.bind(on_release=lambda *_: self._restart())
            self.actions.add_widget(open_btn)
            self.actions.add_widget(share_btn)
            self.actions.add_widget(retry)
        else:
            self.actions.add_widget(self.start_button)

    def _restart(self):
        self.start_button.disabled = False
        self._build_actions_default()
        self._start()

    def _build_actions_default(self):
        self.actions.clear_widgets()
        self.actions.add_widget(self.start_button)

    def _stop_polling(self):
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        self._worker = None
        self.start_button.disabled = True
        self._back.disabled = False  # il worker e' terminato: si puo' tornare
        if self._menu is not None:
            self._menu.disabled = False

    def _exit(self):
        if self._poll is not None:
            self._poll.cancel()
        self._on_back()
