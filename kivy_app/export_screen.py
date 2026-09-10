"""Kivy screen driving the Google Doc generation (ticket 08).

Shows the confirmation summary (ready/total), runs generation on a worker
thread while polling the checkpoint state for a live progress label, then
presents the final document URL and the regenerated document warning when
the previous state pointed to a deleted document.

App bar follows the uniform back+title+kebab hierarchy: exactly one visible
primary action appropriate to the state ("Avvia" before generation, "Apri
documento" after) while the secondary actions (Condividi PDF, Riprendi,
Rigenera nuovo and the global menu) live in the contextual kebab, with the
same confirmation and busy protections as before.

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
"""

from __future__ import annotations

import inspect
import threading

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from .compact_menu import apri_menu
from .export import DocExportError
from .export_layout import (
    export_layout,
    export_overflow_actions,
    export_primary_action,
)
from .launcher import apri_url, condividi_pdf, ultimo_errore
from .material import profile_for_window
from .snackbar import mostra_snackbar


class ExportScreen(BoxLayout):
    def __init__(self, export, on_back, on_menu=None):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8))
        self._export = export
        self._on_back = on_back
        self._on_menu = on_menu
        self._worker: threading.Thread | None = None
        self._url: str | None = None
        self._document_id: str | None = None
        self._poll = None
        self._force_regenerate = False
        self._ui = export_layout(profile_for_window(Window))

        # Uniform app bar: navigation, title and one contextual overflow.
        self.header = BoxLayout(size_hint_y=None, height=dp(self._ui.header_height),
                                spacing=dp(8))
        self._back = Button(text="‹", size_hint_x=None, width=dp(self._ui.back_width))
        self._back.bind(on_release=lambda *_: self._exit())
        self.title = Label(text="Generazione Google Doc", halign="left", valign="middle",
                           shorten=True, shorten_from="right")
        self.title.bind(
            width=lambda _, v: setattr(self.title, "text_size", (v, self.title.height)))
        self._menu = Button(text="⋮", size_hint_x=None, width=dp(self._ui.kebab_width))
        self._menu.bind(on_release=lambda anchor: self._open_export_menu(anchor))
        self.header.add_widget(self._back)
        self.header.add_widget(self.title)
        self.header.add_widget(self._menu)
        self.add_widget(self.header)

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

        # One stretch row, one visible primary action: never overflows.
        self.actions = BoxLayout(size_hint_y=None, height=dp(self._ui.primary_height),
                                 spacing=dp(8))
        self.primary = Button(text=export_primary_action(generated=False))
        self.primary.bind(on_release=lambda *_: self._primary_pressed())
        self.actions.add_widget(self.primary)
        self.add_widget(self.actions)
        self._attached_once = False
        self.bind(parent=self._on_parent_changed)

    @property
    def busy(self):
        return self._worker is not None

    @property
    def generated(self):
        return bool(self._url)

    def apply_text_profile(self):
        """Refresh preset-driven control sizes without changing export state."""
        self._ui = export_layout(profile_for_window(Window))
        self.header.height = dp(self._ui.header_height)
        self._back.width = dp(self._ui.back_width)
        self._menu.width = dp(self._ui.kebab_width)
        self.actions.height = dp(self._ui.primary_height)

    def _on_parent_changed(self, _screen, parent):
        """Re-apply settings when this preserved screen returns to the stack."""
        if parent is None:
            return
        if self._attached_once:
            self.apply_text_profile()
        else:
            self._attached_once = True

    # ------------------------------------------------------------- app bar

    def _open_export_menu(self, anchor):
        """Contextual kebab: secondary actions only, busy protections kept."""
        if self.busy:
            return
        callbacks = {"Rigenera nuovo": self._confirm_regenerate}
        if self.generated:
            callbacks["Condividi PDF"] = self._share_pdf
            callbacks["Riprendi"] = self._restart
        if self._on_menu is not None:
            callbacks["Impostazioni"] = lambda: self._invoke_parent_menu(anchor)
        azioni = export_overflow_actions(generated=self.generated,
                                         include_parent=self._on_menu is not None)
        return apri_menu(((label, callbacks[label]) for label in azioni), anchor=anchor)

    def _invoke_parent_menu(self, anchor):
        """Honor both the legacy zero-arg and the anchor-aware parent contract."""
        if self.busy or self._on_menu is None:
            return None
        try:
            inspect.signature(self._on_menu).bind(anchor)
        except (TypeError, ValueError):
            return self._on_menu()
        return self._on_menu(anchor)

    # ------------------------------------------------------------ primary

    def _primary_pressed(self):
        if self.busy:
            return
        if self.generated:
            if not apri_url(self._url):
                dettaglio = ultimo_errore() or "il launcher non ha aperto l'URL"
                self._show_error(f"Impossibile aprire il documento: {dettaglio}")
        else:
            self._start()

    def _refresh_primary(self):
        self.primary.text = export_primary_action(generated=self.generated)

    def _confirm_regenerate(self):
        if self.busy:
            return
        content = BoxLayout(orientation="vertical")
        content.add_widget(Label(text="Creare un nuovo documento?\nIl precedente resta su Drive."))
        confirm = Button(text="Conferma nuovo documento", size_hint_y=None,
                         height=dp(self._ui.minimum_target))
        cancel = Button(text="Annulla", size_hint_y=None,
                        height=dp(self._ui.minimum_target))
        popup = Popup(title="Rigenerazione", content=content, size_hint=(0.9, None),
                      height=dp(130 + 2 * self._ui.minimum_target))
        def start(*_):
            popup.dismiss()
            self._force_regenerate = True
            self._start()
        confirm.bind(on_release=start)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(confirm)
        content.add_widget(cancel)
        popup.open()

    # ------------------------------------------------------------ worker

    def _start(self):
        if self.busy:
            return
        self._url = None
        self._refresh_primary()
        self._set_busy_ui(True)
        self.progress.text = "0% — avvio…"
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()
        self._poll = Clock.schedule_interval(self._tick, 0.5)

    def _run_worker(self):
        try:
            risultato = self._export.genera(force_regenerate=self._force_regenerate)
            Clock.schedule_once(lambda *_: self._done(risultato), 0)
        except Exception as exc:
            testo = str(exc) if isinstance(exc, DocExportError) else f"Errore: {exc}"
            Clock.schedule_once(lambda _, t=testo: self._failed(t), 0)

    def _tick(self, *_):
        inseriti, totale = self._export.progresso()
        percentuale = int(100 * inseriti / totale) if totale else 0
        self.progress.text = f"{percentuale}% — {inseriti}/{totale} esercizi"

    def _done(self, risultato):
        self._url = risultato.get("url")
        self._document_id = risultato.get("document_id")
        parti = [f"Documento generato: {len(risultato.get('esercizi_inseriti', []))} esercizi inseriti."]
        if risultato.get("documento_rigenerato"):
            parti.append("ATTENZIONE: documento precedente incompleto, cancellato o rigenerato su richiesta; "
                         "creato uno nuovo con URL diverso.")
        salvataggio = risultato.get("salvataggio")
        from core.drive_sync import SyncConflict, UploadResult
        if isinstance(salvataggio, SyncConflict):
            parti.append("Stato salvato nel bundle locale, CONFLITTO su Drive "
                         "(risoluzione in arrivo col ticket 10).")
        elif isinstance(salvataggio, UploadResult):
            parti.append("Stato sincronizzato su Drive.")
        self.progress.text = "\n".join(parti)
        self._stop_polling()
        mostra_snackbar(self, "Documento generato.")

    def _failed(self, testo):
        self._stop_polling()
        self.progress.text = "Premi Avvia per riprovare."
        self._show_error(testo)

    def _restart(self):
        self._start()

    def _stop_polling(self):
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        self._worker = None
        self._force_regenerate = False
        self._set_busy_ui(False)
        self._refresh_primary()

    def _set_busy_ui(self, busy):
        """Keep every escape/action surface consistent with ``self.busy``."""
        self.primary.disabled = busy
        self._back.disabled = busy
        self._menu.disabled = busy

    def _show_error(self, text):
        """Errors require acknowledgement; progress/info remain non-blocking."""
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        label = Label(text=str(text), halign="left", valign="middle")
        label.bind(width=lambda _, value: setattr(label, "text_size", (value, None)))
        close = Button(text="Chiudi", size_hint_y=None,
                       height=dp(self._ui.minimum_target))
        popup = Popup(title="Errore", content=content, size_hint=(0.88, None),
                      height=dp(160 + self._ui.minimum_target))
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(label)
        content.add_widget(close)
        popup.open()
        return popup

    # ---------------------------------------------------------------- PDF

    def _share_pdf(self):
        if self.busy:
            return
        if not self._document_id:
            self._show_error("Il documento generato non ha un ID esportabile.")
            return
        self._set_busy_ui(True)
        self.progress.text = "Esportazione PDF da Google Drive…"
        self._worker = threading.Thread(target=self._run_pdf_worker, daemon=True)
        self._worker.start()

    def _run_pdf_worker(self):
        try:
            path = self._export.esporta_pdf(self._document_id)
            Clock.schedule_once(lambda _, p=path: self._pdf_ready(p), 0)
        except Exception as exc:
            Clock.schedule_once(lambda _, t=f"Errore PDF: {exc}": self._pdf_failed(t), 0)

    def _pdf_ready(self, path):
        self._worker = None
        self._set_busy_ui(False)
        if condividi_pdf(path):
            mostra_snackbar(self, f"PDF pronto: {path.name}")
        else:
            dettaglio = ultimo_errore() or "il sistema non ha aperto la condivisione"
            self._show_error(f"Condivisione PDF fallita: {dettaglio}")
        self._refresh_primary()

    def _pdf_failed(self, text):
        self._worker = None
        self._set_busy_ui(False)
        self._show_error(text)
        self._refresh_primary()

    def _exit(self):
        if self.busy:
            return
        if self._poll is not None:
            self._poll.cancel()
        self._on_back()
