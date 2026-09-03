"""Kivy screen for choosing the video and frames of one exercise (ticket 07).

Functional parity with the Streamlit "Video & Frame" tab: search results with
title/duration and selection, manual URL override, timestamp fields with the
10%/50% heuristic proposal, extraction through the platform backend, frame
previews, per-side percentage crop with ``*_orig.jpg`` backup and restore,
and user image import for START/FINISH.

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
"""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage, Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput

from .file_picker import choose_file
from .media import MediaFlowError


def _formatta_durata(secondi) -> str:
    if secondi is None:
        return "n/d"
    secondi = int(secondi)
    return f"{secondi // 60}:{secondi % 60:02d}"


class MediaScreen(BoxLayout):
    def __init__(self, media, on_back):
        super().__init__(orientation="vertical", padding=10, spacing=6)
        self._media = media
        self._on_back = on_back
        self._busy = False

        header = BoxLayout(size_hint_y=None, height=44, spacing=8)
        self._back = Button(text="< Editor", size_hint_x=None, width=120)
        self._back.bind(on_release=lambda *_: self._on_back())
        self.status = Label(text="", halign="left", shorten=True, shorten_from="right")
        header.add_widget(self._back)
        header.add_widget(self.status)
        self.add_widget(header)

        body = ScrollView()
        self.column = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        self.column.bind(minimum_height=self.column.setter("height"))
        body.add_widget(self.column)
        self.add_widget(body)

        self._build_video_section()
        self._build_frame_section()
        self._refresh_status()

    # ------------------------------------------------------------- video

    def _build_video_section(self):
        video_line = BoxLayout(size_hint_y=None, height=40, spacing=4)
        self.video_label = Label(text=f"Video: {self._media.video_url or 'nessuno'}",
                                 halign="left", shorten=True, shorten_from="right")
        search = Button(text="Cerca", size_hint_x=None, width=100)
        search.bind(on_release=lambda *_: self._run_async(self._do_search))
        manual = Button(text="URL manuale", size_hint_x=None, width=130)
        manual.bind(on_release=lambda *_: self._manual_url_popup())
        extract = Button(text="Estrai frame", size_hint_x=None, width=130)
        extract.bind(on_release=lambda *_: self._run_async(self._do_extract))
        video_line.add_widget(self.video_label)
        video_line.add_widget(search)
        video_line.add_widget(manual)
        video_line.add_widget(extract)
        self.column.add_widget(video_line)

        ts_line = BoxLayout(size_hint_y=None, height=40, spacing=4)
        ts_line.add_widget(Label(text="Start s", size_hint_x=None, width=80))
        self.ts_start = TextInput(text=self._ts_text(self._media.ts_start),
                                  multiline=False, size_hint_x=None, width=90)
        self.ts_start.bind(focus=self._ts_handler("ts_start", self.ts_start))
        ts_line.add_widget(self.ts_start)
        ts_line.add_widget(Label(text="Finish s", size_hint_x=None, width=80))
        self.ts_finish = TextInput(text=self._ts_text(self._media.ts_finish),
                                   multiline=False, size_hint_x=None, width=90)
        self.ts_finish.bind(focus=self._ts_handler("ts_finish", self.ts_finish))
        ts_line.add_widget(self.ts_finish)
        heuristic = Button(text="EURISTICA 10%/50%", size_hint_x=None, width=160)
        heuristic.bind(on_release=lambda *_: self._apply_heuristic())
        ts_line.add_widget(heuristic)
        self.column.add_widget(ts_line)

        self.results = BoxLayout(orientation="vertical", spacing=4)
        self.column.add_widget(self.results)
        self._render_results()

    def _ts_text(self, valore) -> str:
        return "" if valore is None else f"{float(valore):.1f}"

    def _ts_handler(self, chiave, campo):
        def on_focus(instance, focused):
            if focused:
                return
            testo = campo.text.strip().replace(",", ".")
            if not testo:
                return
            try:
                valore = float(testo)
            except ValueError:
                self.status.text = f"Timestamp non numerico: {testo}"
                campo.text = self._ts_text(getattr(self._media, chiave))
                return
            try:
                self._media.imposta_timestamp(**{chiave: valore})
            except MediaFlowError as exc:
                self.status.text = str(exc)
            self._refresh_status()
        return on_focus

    def _apply_heuristic(self):
        if not self._media.video_url:
            self.status.text = "Seleziona prima un video."
            return
        self._run_async(self._do_heuristic)

    def _do_heuristic(self):
        self._media.proponi_euristica()
        Clock.schedule_once(lambda *_: self._sync_video_widgets(), 0)

    def _do_search(self):
        self._media.cerca()
        Clock.schedule_once(lambda *_: self._render_results(), 0)

    def _render_results(self, *_):
        self.results.clear_widgets()
        for indice, scelta in enumerate(self._media.scelte):
            row = BoxLayout(size_hint_y=None, height=44, spacing=6)
            info = Button(text=f"{indice + 1}. {scelta.title[:60]} ({_formatta_durata(scelta.duration)})",
                          )
            info.bind(on_release=lambda _, i=indice: self._run_async(lambda: self._choose(i)))
            video_id = (scelta.url.split("v=")[-1] if "v=" in scelta.url
                        else scelta.url.rstrip("/").split("/")[-1])[:11]
            preview = AsyncImage(source=f"https://img.youtube.com/vi/{video_id}/default.jpg",
                                 fit_mode="contain", size_hint_x=None, width=100)
            row.add_widget(preview)
            row.add_widget(info)
            self.results.add_widget(row)

    def _choose(self, indice):
        self._media.seleziona(indice)
        Clock.schedule_once(lambda *_: self._sync_video_widgets(), 0)

    def _do_extract(self):
        self._media.estrai()
        Clock.schedule_once(lambda *_: (self._sync_video_widgets(),
                                        self._refresh_frames()), 0)

    def _manual_url_popup(self):
        input_url = TextInput(hint_text="https://www.youtube.com/watch?v=...",
                              multiline=False)
        buttons = BoxLayout(size_hint_y=None, height=44, spacing=8)
        content = BoxLayout(orientation="vertical", spacing=6)
        popup = Popup(title="URL video manuale", content=content, size_hint=(0.9, 0.35))
        ok = Button(text="Imposta")
        cancel = Button(text="Annulla")
        content.add_widget(input_url)
        content.add_widget(buttons)
        buttons.add_widget(ok)
        buttons.add_widget(cancel)
        ok.bind(on_release=lambda *_: self._apply_manual_url(input_url.text, popup))
        cancel.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _apply_manual_url(self, url, popup):
        popup.dismiss()
        try:
            self._media.url_manuale(url)
        except MediaFlowError as exc:
            self.status.text = str(exc)
            return
        self._sync_video_widgets()
        self._refresh_status()

    def _sync_video_widgets(self):
        self.video_label.text = f"Video: {self._media.video_url or 'nessuno'}"
        self.ts_start.text = self._ts_text(self._media.ts_start)
        self.ts_finish.text = self._ts_text(self._media.ts_finish)

    # ------------------------------------------------------------- frames

    def _build_frame_section(self):
        self.frames_row = BoxLayout(size_hint_y=None, height=340, spacing=8)
        for suffisso in ("start", "finish"):
            panel = BoxLayout(orientation="vertical", spacing=2)
            preview = Image(source=self._media.frame(suffisso) or "",
                            fit_mode="contain", size_hint_y=1)
            panel.add_widget(preview)
            setattr(self, f"preview_{suffisso}", preview)
            sliders = {}
            lato_line = BoxLayout(size_hint_y=None, height=90, spacing=2)
            for lato in ("sinistra", "alto", "destra", "basso"):
                box = BoxLayout(orientation="vertical")
                box.add_widget(Label(text=lato, size_hint_y=None, height=20))
                slider = Slider(min=0, max=45, value=0, orientation="vertical")
                box.add_widget(slider)
                sliders[lato] = slider
                lato_line.add_widget(box)
            for slider in sliders.values():
                slider.bind(on_value=self._preview_handler(suffisso, sliders))
            self._preview_jobs = getattr(self, "_preview_jobs", {})
            panel.add_widget(lato_line)
            actions = BoxLayout(size_hint_y=None, height=40, spacing=4)
            apply = Button(text="Applica")
            apply.bind(on_release=lambda _, s=suffisso, sl=sliders: self._apply_crop(s, sl))
            restore = Button(text="Ripristina")
            restore.bind(on_release=lambda _, s=suffisso: self._restore(s))
            import_btn = Button(text="Immagine…", size_hint_x=None, width=110)
            import_btn.bind(on_release=lambda _, s=suffisso: self._import_image(s))
            actions.add_widget(apply)
            actions.add_widget(restore)
            actions.add_widget(import_btn)
            panel.add_widget(actions)
            self.frames_row.add_widget(panel)
        self.column.add_widget(self.frames_row)

    def _preview_handler(self, suffisso, sliders):
        def on_value(*_):
            job = self._preview_jobs.get(suffisso)
            if job is not None:
                Clock.unschedule(job)
            self._preview_jobs[suffisso] = Clock.schedule_once(
                lambda *_: self._render_preview(suffisso, sliders), 0.2)
        return on_value

    def _render_preview(self, suffisso, sliders):
        self._preview_jobs[suffisso] = None
        preview = getattr(self, f"preview_{suffisso}")
        try:
            anteprima = self._media.anteprima_crop(
                suffisso, sliders["sinistra"].value, sliders["alto"].value,
                sliders["destra"].value, sliders["basso"].value)
        except (MediaFlowError, ValueError, OSError) as exc:
            self.status.text = str(exc)
            return
        preview.source = anteprima
        preview.reload()

    def _apply_crop(self, suffisso, sliders):
        try:
            self._media.ritaglia(suffisso, sliders["sinistra"].value,
                                 sliders["alto"].value, sliders["destra"].value,
                                 sliders["basso"].value)
        except MediaFlowError as exc:
            self.status.text = str(exc)
            return
        except ValueError as exc:  # vincoli percentuali di box_ritaglio
            self.status.text = str(exc)
            return
        self.status.text = "Ritaglio applicato."
        for slider in sliders.values():
            slider.value = 0
        self._refresh_frames()

    def _restore(self, suffisso):
        try:
            self._media.ripristina(suffisso)
        except MediaFlowError as exc:
            self.status.text = str(exc)
            return
        self.status.text = "Originale ripristinato."
        self._refresh_frames()

    def _import_image(self, suffisso):
        def on_result(percorso):
            if not percorso:
                return
            try:
                self._media.importa_immagine(percorso, suffisso)
            except MediaFlowError as exc:
                testo = str(exc)
                Clock.schedule_once(lambda _, testo=testo: self._set_status(testo), 0)
                return
            Clock.schedule_once(lambda *_: (self._refresh_frames(),
                                            self._refresh_status()), 0)
        choose_file(on_result, title=f"Scegli immagine {suffisso.upper()}",
                    patterns=[("Immagini", ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"])])

    def _refresh_frames(self):
        for suffisso in ("start", "finish"):
            preview = getattr(self, f"preview_{suffisso}")
            preview.source = self._media.frame(suffisso) or ""
            preview.reload()

    def _set_status(self, testo):
        self.status.text = testo

    # ------------------------------------------------------------- async

    def _run_async(self, operation):
        if self._busy:
            self.status.text = "Attendere: operazione in corso…"
            return
        self._busy = True
        self._back.disabled = True  # niente ritorno (e niente Salva) durante il worker
        self.status.text = "Elaboro…"

        def worker():
            try:
                operation()
                Clock.schedule_once(lambda *_: self._finish_async(None), 0)
            except Exception as exc:
                # eccoti il messaggio materializzato SUBITO: fuori dal blocco
                # except il nome exc verrebbe cancellato e la lambda romperebbe.
                testo = str(exc) if isinstance(exc, MediaFlowError) else f"Errore imprevisto: {exc}"
                Clock.schedule_once(lambda _, testo=testo: self._finish_async(testo), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_async(self, errore):
        self._busy = False
        self._back.disabled = False
        self.status.text = errore if errore else ""
        if not errore:
            self._refresh_status()

    def _refresh_status(self):
        self.status.text = (
            f"{self._media.titolo_video or self._media.video_url or 'nessun video'} — "
            f"frame: {'OK' if self._media.pronto() else 'da estrarre'}"
        )
