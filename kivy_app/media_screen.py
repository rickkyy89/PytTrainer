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
from kivy.core.window import Window

from .file_picker import choose_file
from .launcher import apri_url
from .media import MediaFlowError
from .material import profile_for_window
from .media_layout import media_layout


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
        self._ui = media_layout(profile_for_window(Window, input_mode="touch"))

        header = BoxLayout(size_hint_y=None, height=44, spacing=8)
        self._back = Button(text="< Editor", size_hint_x=None, width=120)
        self._back.bind(on_release=lambda *_: self._on_back())
        self.status = Label(text="", halign="left", valign="middle",
                            shorten=True, shorten_from="right")
        self.status.bind(
            width=lambda _, v: setattr(self.status, "text_size", (v, self.status.height)))
        header.add_widget(self._back)
        header.add_widget(self.status)
        self.add_widget(header)

        body = ScrollView()
        self._scroll = body
        self.column = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        self.column.bind(minimum_height=self.column.setter("height"))
        body.add_widget(self.column)
        self.add_widget(body)

        self._build_video_section()
        self._build_frame_section()
        self._syncing = False
        self._refresh_status()
        if self._media.video_url and self._media.durata is None:
            # video proveniente dal manifest: la pista scrub non conosce la
            # durata, va risolta in background prima di poterla usare
            self._run_async(self._do_durata)

    def _do_durata(self):
        self._media.assicura_durata()
        Clock.schedule_once(lambda *_: self._sync_scrub_sliders(), 0)

    # ------------------------------------------------------------- video

    def _build_video_section(self):
        video_line = BoxLayout(size_hint_y=None, height=40, spacing=4)
        self.video_label = Label(text=f"Video: {self._media.video_url or 'nessuno'}",
                                 halign="left", valign="middle",
                                 shorten=True, shorten_from="right")
        self.video_label.bind(
            width=lambda _, v: setattr(self.video_label, "text_size", (v, self.video_label.height)))
        play = Button(text="Play", size_hint_x=None, width=80)
        play.bind(on_release=lambda *_: self._play())
        search = Button(text="Cerca", size_hint_x=None, width=100)
        search.bind(on_release=lambda *_: self._run_async(self._do_search))
        manual = Button(text="URL manuale", size_hint_x=None, width=130)
        manual.bind(on_release=lambda *_: self._manual_url_popup())
        extract = Button(text="Estrai frame", size_hint_x=None, width=130)
        extract.bind(on_release=lambda *_: self._run_async(self._do_extract))
        video_line.add_widget(self.video_label)
        video_line.add_widget(play)
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

        self.results = BoxLayout(orientation="vertical", spacing=4, size_hint_y=None)
        self.results.bind(minimum_height=self.results.setter("height"))
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
                return
            # allinea la pista e aggiorna la preview sul nuovo secondo
            self._sync_scrub_sliders()
            self._mostra_scrub(chiave.split("_", 1)[1])
            self._refresh_status()
        return on_focus

    def _mostra_scrub(self, suffisso):
        slider = self._scrub_slider.get(suffisso)
        if slider is None or slider.disabled or not self._media.video_url:
            return
        self._scrub_pendente[suffisso] = float(slider.value)
        self._scrub_anteprima(suffisso)

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
        # forza la riestrazione: dopo un cambio video i frame vecchi sono ancora
        # su disco e ``estrai()`` senza riestrai li terrebbe (ritornando presto)
        self._media.estrai(riestrai=True)
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
        self._sync_scrub_sliders()

    # ------------------------------------------------------------- frames

    def _build_frame_section(self):
        self.frames_row = BoxLayout(
            orientation=self._ui.frame_axis, size_hint_y=None,
            height=390 if self._ui.frame_axis == "horizontal" else 780, spacing=8)
        self._scrub_jobs: dict[str, object] = {}
        self._scrub_generazioni: dict[str, int] = {}
        self._scrub_pendente: dict[str, float] = {}
        self._scrub_in_corso: dict[str, float] = {}
        self._scrub_in_volo: set[str] = set()
        self._scrub_slider: dict[str, Slider] = {}
        for suffisso in ("start", "finish"):
            panel = BoxLayout(orientation="vertical", spacing=2)
            preview = Image(source=self._media.frame(suffisso) or "",
                            fit_mode="contain", size_hint_y=1)
            panel.add_widget(preview)
            setattr(self, f"preview_{suffisso}", preview)
            panel.add_widget(self._build_scrub(suffisso))
            sliders = {}
            lato_line = BoxLayout(size_hint_y=None, height=max(90, self._ui.target_minimum * 2), spacing=2)
            for lato in ("sinistra", "alto", "destra", "basso"):
                box = BoxLayout(orientation="vertical")
                box.add_widget(Label(text=lato, size_hint_y=None, height=20))
                slider = Slider(min=0, max=45, value=0, orientation="vertical")
                self._blocca_scroll(slider)
                box.add_widget(slider)
                sliders[lato] = slider
                lato_line.add_widget(box)
            for slider in sliders.values():
                slider.bind(on_value=self._preview_handler(suffisso, sliders))
            self._preview_jobs = getattr(self, "_preview_jobs", {})
            panel.add_widget(lato_line)
            actions = BoxLayout(size_hint_y=None, height=self._ui.target_minimum, spacing=4)
            apply = Button(text="Applica")
            apply.bind(on_release=lambda _, s=suffisso, sl=sliders: self._apply_crop(s, sl))
            restore = Button(text="Ripristina")
            restore.bind(on_release=lambda _, s=suffisso: self._restore(s))
            import_btn = Button(text="Immagine…", size_hint_x=None, width=self._ui.target_minimum * 2)
            import_btn.bind(on_release=lambda _, s=suffisso: self._import_image(s))
            actions.add_widget(apply)
            actions.add_widget(restore)
            actions.add_widget(import_btn)
            panel.add_widget(actions)
            self.frames_row.add_widget(panel)
        self.column.add_widget(self.frames_row)
        self._sync_scrub_sliders()

    def _blocca_scroll(self, slider):
        """Il drag su uno slider non deve far scorrere la pagina."""
        def down(inst, touch):
            if slider.collide_point(*touch.pos):
                self._scroll.do_scroll_y = False
                self._scroll.do_scroll_x = False
            return False  # non consumare: lo slider deve ricevere il tocco

        def up(inst, touch):
            self._scroll.do_scroll_y = True
            self._scroll.do_scroll_x = True
            return False

        slider.bind(on_touch_down=down, on_touch_up=up)

    def _build_scrub(self, suffisso: str):
        barra = BoxLayout(orientation="vertical", size_hint_y=None, height=66, spacing=0)
        etichetta = Label(
            text=self._scrub_testo(getattr(self._media, f"ts_{suffisso}")),
            size_hint_y=None, height=20, font_size="13sp", halign="left")
        barra.add_widget(etichetta)
        setattr(self, f"scrub_etichetta_{suffisso}", etichetta)
        slider = Slider(min=0, max=1, value=0, size_hint_y=None, height=44)
        self._blocca_scroll(slider)
        slider.bind(on_value=self._scrub_handler(suffisso, slider))
        slider.bind(on_touch_up=lambda _, touch, s=suffisso, sl=slider:
                    self._scrub_release(s, sl, touch))
        barra.add_widget(slider)
        self._scrub_slider[suffisso] = slider
        return barra

    def _play(self):
        try:
            url = self._media.url_per_play()
        except MediaFlowError as exc:
            self.status.text = str(exc)
            return
        if apri_url(url):
            self.status.text = f"Play dal punto START nel player di sistema: {url}"
        else:
            self.status.text = f"Nessun player disponibile per aprire: {url}"

    def _scrub_testo(self, valore) -> str:
        durata = self._media.durata
        base = f"Tempo: {'' if valore is None else f'{float(valore):.1f}'} s"
        return f"{base}   (video: {_formatta_durata(durata) if durata else 'durata n/d'})"

    def _scrub_handler(self, suffisso, slider):
        def on_value(*_):
            getattr(self, f"scrub_etichetta_{suffisso}").text = self._scrub_testo(slider.value)
            if self._syncing or slider.disabled or not self._media.video_url:
                return
            self._scrub_pendente[suffisso] = float(slider.value)
            vecchio = self._scrub_jobs.get(suffisso)
            if vecchio is not None:
                Clock.unschedule(vecchio)
            self._scrub_jobs[suffisso] = Clock.schedule_once(
                lambda *_: self._scrub_anteprima(suffisso), 0.25)
        return on_value

    def _scrub_anteprima(self, suffisso):
        self._scrub_jobs[suffisso] = None
        valore = self._scrub_pendente.get(suffisso)
        if valore is None:
            return
        if suffisso in self._scrub_in_volo or self._busy:
            # estrazione gia' partita o flusso occupato: riprova col valore corrente
            self._scrub_jobs[suffisso] = Clock.schedule_once(
                lambda *_: self._scrub_anteprima(suffisso), 0.2)
            return
        self._scrub_in_volo.add(suffisso)
        generazione = self._scrub_generazioni.get(suffisso, 0) + 1
        self._scrub_generazioni[suffisso] = generazione
        self._scrub_in_corso[suffisso] = valore

        def worker():
            try:
                percorso = self._media.anteprima_scrub(suffisso, valore)
                Clock.schedule_once(
                    lambda *_: self._scrub_fatto(suffisso, generazione, percorso, None), 0)
            except Exception as exc:
                testo = (str(exc) if isinstance(exc, MediaFlowError)
                         else f"Errore imprevisto: {exc}")
                Clock.schedule_once(
                    lambda *_: self._scrub_fatto(suffisso, generazione, None, testo), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _scrub_fatto(self, suffisso, generazione, percorso, errore):
        self._scrub_in_volo.discard(suffisso)
        if errore:
            self.status.text = errore
        elif generazione == self._scrub_generazioni.get(suffisso):
            # mostra SEMPRE l'ultimo frame richiesto, anche se un frame reale
            # esiste gia': lo scrub serve proprio a sceglierne uno nuovo
            preview = getattr(self, f"preview_{suffisso}")
            preview.source = percorso
            preview.reload()
        # se nel frattempo l'utente ha spostato la pista, recupera l'ultimo valore
        pendente = self._scrub_pendente.get(suffisso)
        in_corso = self._scrub_in_corso.get(suffisso)
        if pendente is not None and (in_corso is None or abs(pendente - in_corso) > 0.01):
            self._scrub_anteprima(suffisso)

    def _scrub_release(self, suffisso, slider, touch=None):
        if slider.disabled or not self._media.video_url:
            return
        if touch is not None and not slider.collide_point(*touch.pos):
            return  # tocco nato altrove (scroll della pagina): non committare
        try:
            self._media.imposta_timestamp(**{f"ts_{suffisso}": float(slider.value)})
        except MediaFlowError as exc:
            self.status.text = str(exc)
            return
        getattr(self, f"ts_{'start' if suffisso == 'start' else 'finish'}").text = \
            self._ts_text(slider.value)
        # assicurati che la posizione finale venga mostrata anche se il
        # debounce non e' mai partito (click secco sulla pista)
        self._scrub_pendente[suffisso] = float(slider.value)
        vecchio = self._scrub_jobs.get(suffisso)
        if vecchio is not None:
            Clock.unschedule(vecchio)
        self._scrub_jobs[suffisso] = None
        self._scrub_anteprima(suffisso)
        self._refresh_status()

    def _sync_scrub_sliders(self):
        durata = self._media.durata or 0
        self._syncing = True
        try:
            for suffisso, slider in self._scrub_slider.items():
                valore = getattr(self._media, f"ts_{suffisso}")
                if durata > 0 and self._media.video_url:
                    slider.max = float(durata)
                    slider.disabled = False
                    slider.value = min(max(float(valore or 0), 0), slider.max)
                    # il campo testo e la pista devono coincidere: correggi un ts
                    # fuori scala lasciato da un video precedente
                    if valore is None or abs(float(valore) - slider.value) > 0.05:
                        self._media.imposta_timestamp(**{f"ts_{suffisso}": slider.value})
                        getattr(self, f"ts_{'start' if suffisso == 'start' else 'finish'}").text = \
                            self._ts_text(slider.value)
                else:
                    slider.disabled = True
                getattr(self, f"scrub_etichetta_{suffisso}").text = self._scrub_testo(slider.value)
        finally:
            self._syncing = False

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
