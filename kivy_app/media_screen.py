"""Kivy screen for choosing the video and frames of one exercise (ticket 07).

Functional parity with the Streamlit "Video & Frame" tab: search results with
title/duration and selection, manual URL override, timestamp fields with the
10%/50% heuristic proposal, extraction through the platform backend, frame
previews, per-side percentage crop with ``*_orig.jpg`` backup and restore,
user image import, placeholder frames and a 5:4 free-hand drawing popup for
START/FINISH.

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
"""

from __future__ import annotations

import os
import threading

from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import AsyncImage, Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.core.window import Window

from .file_picker import choose_file
from .fine_slider import FineSlider
from .launcher import apri_url, ultimo_errore
from .media import MediaFlowError
from .material import profile_for_window
from .media_layout import media_layout


def _formatta_durata(secondi) -> str:
    if secondi is None:
        return "n/d"
    secondi = int(secondi)
    return f"{secondi // 60}:{secondi % 60:02d}"


class _TelaDisegno(Widget):
    """Foglio bianco 5:4 per disegnare a mano un frame START/FINISH.

    Dito, penna e mouse arrivano tutti da ``on_touch_*`` con il grab del
    touch: il tratto e' nero e i punti sono salvati in coordinate
    normalizzate 0..1 (y verso il basso, come nei pixel dell'immagine),
    cosi' l'export PNG 5:4 e il ridimensionamento del popup non deformano
    ne' perdono nulla.
    """

    LARGHEZZA_EXPORT = 1000
    ALTEZZA_EXPORT = 800  # 5:4 come i placeholder estratti dal controller
    SPESSORE_EXPORT = 6   # pixel di tratto su LARGHEZZA_EXPORT

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        super().__init__(**kwargs)
        self.tratti: list[list[tuple[float, float]]] = []
        self._istruzioni: list = []
        self._linea_corrente: Line | None = None
        self._touch = None
        with self.canvas:
            Color(1, 1, 1, 1)
            self._sfondo = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._aggiorna, size=self._aggiorna)

    # ------------------------------------------------------------- disegno

    def on_touch_down(self, touch):
        if self._touch is not None or not self.collide_point(*touch.pos):
            return False
        if getattr(touch, "button", None) not in (None, "left"):
            return False  # mouse: solo il tasto sinistro traccia (destra/rotella ignora)
        self._touch = touch
        touch.grab(self)
        self.tratti.append([self._punto_norm(touch)])
        self._ridisegna()
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self or touch is not self._touch:
            return False
        self.tratti[-1].append(self._punto_norm(touch))
        if self._linea_corrente is not None:
            self._linea_corrente.points = self._punti_schermo(self.tratti[-1])
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self or touch is not self._touch:
            return False
        touch.ungrab(self)
        self._touch = None
        return True

    def annulla_tratto(self):
        """Rimuove l'ultimo tratto disegnato."""
        if self.tratti:
            self.tratti.pop()
            self._ridisegna()

    def pulisci(self):
        self.tratti = []
        self._ridisegna()

    # -------------------------------------------------------------- render

    def _punto_norm(self, touch) -> tuple[float, float]:
        nx = min(max((touch.x - self.x) / max(self.width, 1), 0.0), 1.0)
        ny = min(max(1.0 - (touch.y - self.y) / max(self.height, 1), 0.0), 1.0)
        return nx, ny

    def _punti_schermo(self, tratto) -> list[float]:
        punti = []
        for nx, ny in tratto:
            punti.extend((self.x + nx * self.width, self.y + (1 - ny) * self.height))
        return punti if len(punti) > 2 else punti * 2  # il tap singolo diventi un segmento

    def _spessore_display(self) -> float:
        return max(2.0, self.width * self.SPESSORE_EXPORT / self.LARGHEZZA_EXPORT)

    def _aggiorna(self, *_):
        self._sfondo.pos = self.pos
        self._sfondo.size = self.size
        self._ridisegna()

    def _ridisegna(self, *_):
        for istruzione in self._istruzioni:
            self.canvas.remove(istruzione)
        self._istruzioni = []
        self._linea_corrente = None
        spessore = self._spessore_display()
        for tratto in self.tratti:
            with self.canvas:
                colore = Color(0, 0, 0, 1)
                linea = Line(points=self._punti_schermo(tratto), width=spessore)
            self._istruzioni.extend((colore, linea))
            self._linea_corrente = linea

    # --------------------------------------------------------------- export

    def esporta_png(self, percorso: str) -> str:
        """Rasterizza i tratti su un PNG bianco 5:4 leggibile da importa_immagine."""
        from PIL import Image as ApriImmagine, ImageDraw  # locale: ``Image`` e' gia' Kivy
        immagine = ApriImmagine.new("RGB", (self.LARGHEZZA_EXPORT, self.ALTEZZA_EXPORT), "white")
        disegno = ImageDraw.Draw(immagine)
        raggio = self.SPESSORE_EXPORT / 2.0
        for tratto in self.tratti:
            punti = [(nx * self.LARGHEZZA_EXPORT, ny * self.ALTEZZA_EXPORT)
                     for nx, ny in tratto]
            if len(punti) == 1:
                x, y = punti[0]
                disegno.ellipse((x - raggio, y - raggio, x + raggio, y + raggio),
                                fill=(0, 0, 0))
            else:
                disegno.line(punti, fill=(0, 0, 0), width=self.SPESSORE_EXPORT,
                             joint="curve")
        immagine.save(percorso, "PNG")
        return percorso


class MediaScreen(BoxLayout):
    def __init__(self, media, on_back, on_menu=None):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6))
        self._media = media
        self._on_back = on_back
        self._on_menu = on_menu
        self._busy = False
        self._profile = profile_for_window(Window)
        self._ui = media_layout(self._profile)

        header = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        if self._on_menu is not None:
            self._menu = Button(text="Menu", size_hint_x=None, width=dp(82))
            self._menu.bind(on_release=lambda *_: self._on_menu())
            header.add_widget(self._menu)
        else:
            self._menu = None
        self._back = Button(text="< Editor", size_hint_x=None, width=dp(120))
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
        self.column = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
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
        video_line = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
        self.video_label = Label(text=f"Video: {self._media.video_url or 'nessuno'}",
                                 halign="left", valign="middle",
                                 shorten=True, shorten_from="right")
        self.video_label.bind(
            width=lambda _, v: setattr(self.video_label, "text_size", (v, self.video_label.height)))
        play = Button(text="Play", size_hint_x=None, width=dp(80))
        play.bind(on_release=lambda *_: self._play())
        search = Button(text="Cerca", size_hint_x=None, width=dp(100))
        search.bind(on_release=lambda *_: self._run_async(self._do_search))
        manual = Button(text="URL manuale", size_hint_x=None, width=dp(130))
        manual.bind(on_release=lambda *_: self._manual_url_popup())
        extract = Button(text="Estrai frame", size_hint_x=None, width=dp(130))
        extract.bind(on_release=lambda *_: self._run_async(self._do_extract))
        video_line.add_widget(self.video_label)
        video_line.add_widget(play)
        video_line.add_widget(search)
        video_line.add_widget(manual)
        video_line.add_widget(extract)
        self.column.add_widget(video_line)

        row_h = dp(max(56, self._ui.target_minimum))
        ts_line = BoxLayout(size_hint_y=None, height=row_h, spacing=dp(4), padding=[dp(8), dp(6)])
        self._tinta_riquadro(ts_line)
        ts_line.add_widget(Label(text="Start s", size_hint_x=None, width=dp(96),
                                 halign="left", valign="middle"))
        self.ts_start = TextInput(text=self._ts_text(self._media.ts_start),
                                  multiline=False, size_hint_x=None, width=dp(110))
        self.ts_start.bind(focus=self._ts_handler("ts_start", self.ts_start))
        ts_line.add_widget(self.ts_start)
        ts_line.add_widget(Label(text="Finish s", size_hint_x=None, width=dp(110),
                                 halign="left", valign="middle"))
        self.ts_finish = TextInput(text=self._ts_text(self._media.ts_finish),
                                    multiline=False, size_hint_x=None, width=dp(110))
        self.ts_finish.bind(focus=self._ts_handler("ts_finish", self.ts_finish))
        ts_line.add_widget(self.ts_finish)
        heuristic = Button(text="EURISTICA 10%/50%", size_hint_x=None, width=dp(170))
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

    def _tinta_riquadro(self, contenitore):
        from kivy.graphics import Color, Rectangle
        with contenitore.canvas.before:
            Color(0.13, 0.15, 0.17, 1)
            retta = Rectangle(pos=contenitore.pos, size=contenitore.size)

        def follow(*_):
            retta.pos = contenitore.pos
            retta.size = contenitore.size

        contenitore.bind(pos=follow, size=follow)

    def _render_results(self, *_):
        self.results.clear_widgets()
        for indice, scelta in enumerate(self._media.scelte):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            info = Button(text=f"{indice + 1}. {scelta.title[:60]} ({_formatta_durata(scelta.duration)})",
                          halign="left", valign="middle", shorten=True)
            info.bind(width=lambda _, v, b=info: setattr(b, "text_size", (max(v - dp(20), 10), b.height)),
                      height=lambda _, h, b=info: setattr(b, "text_size", (max(b.width - dp(20), 10), h)))
            info.bind(on_release=lambda _, i=indice: self._run_async(lambda: self._choose(i)))
            video_id = (scelta.url.split("v=")[-1] if "v=" in scelta.url
                        else scelta.url.rstrip("/").split("/")[-1])[:11]
            preview = AsyncImage(source=f"https://img.youtube.com/vi/{video_id}/default.jpg",
                                 fit_mode="contain", size_hint_x=None, width=dp(100))
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
        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        content = BoxLayout(orientation="vertical", spacing=dp(6))
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
        anteprima_min = self._profile.tokens.dimensions["frame_min_height"]
        scrub_h = 72
        lato_h = max(90, self._ui.target_minimum * 2)
        # due righe di azioni: cinque pulsanti su una sola linea schiacciano
        # le etichette (soprattutto su compact) rendendoli poco accessibili
        azioni_h = self._ui.target_minimum * 2 + 4
        # altezza di UN pannello START/FINISH completo (preview + scrub + crop
        # + azioni, con un po' di margine per gli spacing interni del pannello)
        pannello_h = anteprima_min + scrub_h + lato_h + azioni_h + 24
        # in compact i due pannelli si impilano (asse verticale): la riga deve
        # contenerne DUE piu' lo spacing, non dividere l'altezza di uno
        altezza_riga = pannello_h * 2 + 8 if self._ui.frame_axis == "vertical" else pannello_h
        self.frames_row = BoxLayout(
            orientation=self._ui.frame_axis, size_hint_y=None,
            height=dp(altezza_riga), spacing=dp(8))
        self._scrub_jobs: dict[str, object] = {}
        self._scrub_generazioni: dict[str, int] = {}
        self._scrub_pendente: dict[str, float] = {}
        self._scrub_in_corso: dict[str, float] = {}
        self._scrub_in_volo: set[str] = set()
        self._scrub_slider: dict[str, Slider] = {}
        for suffisso in ("start", "finish"):
            panel = BoxLayout(orientation="vertical", spacing=dp(2))
            preview = Image(source=self._media.frame(suffisso) or "",
                            fit_mode="contain", size_hint_y=1, nocache=True)
            panel.add_widget(preview)
            setattr(self, f"preview_{suffisso}", preview)
            panel.add_widget(self._build_scrub(suffisso))
            sliders = {}
            lato_line = BoxLayout(size_hint_y=None, height=dp(max(90, self._ui.target_minimum * 2)), spacing=dp(2))
            for lato in ("sinistra", "alto", "destra", "basso"):
                box = BoxLayout(orientation="vertical")
                box.add_widget(Label(text=lato, size_hint_y=None, height=dp(24)))
                slider = Slider(min=0, max=45, value=0, orientation="vertical")
                self._blocca_scroll(slider)
                box.add_widget(slider)
                sliders[lato] = slider
                lato_line.add_widget(box)
            for slider in sliders.values():
                slider.bind(on_value=self._preview_handler(suffisso, sliders))
            self._preview_jobs = getattr(self, "_preview_jobs", {})
            panel.add_widget(lato_line)
            apply = Button(text="Applica")
            apply.bind(on_release=lambda _, s=suffisso, sl=sliders: self._apply_crop(s, sl))
            restore = Button(text="Ripristina")
            restore.bind(on_release=lambda _, s=suffisso: self._restore(s))
            import_btn = Button(text="Immagine…", size_hint_x=None, width=dp(self._ui.target_minimum * 2))
            import_btn.bind(on_release=lambda _, s=suffisso: self._import_image(s))
            placeholder_btn = Button(text="Placeholder")
            placeholder_btn.bind(on_release=lambda _, s=suffisso: self._placeholder(s))
            draw_btn = Button(text="Disegna")
            draw_btn.bind(on_release=lambda _, s=suffisso: self._apri_disegno(s))
            azioni_sopra = BoxLayout(size_hint_y=None,
                                      height=dp(self._ui.target_minimum), spacing=dp(4))
            azioni_sopra.add_widget(apply)
            azioni_sopra.add_widget(restore)
            azioni_sotto = BoxLayout(size_hint_y=None,
                                     height=dp(self._ui.target_minimum), spacing=dp(4))
            azioni_sotto.add_widget(import_btn)
            azioni_sotto.add_widget(placeholder_btn)
            azioni_sotto.add_widget(draw_btn)
            panel.add_widget(azioni_sopra)
            panel.add_widget(azioni_sotto)
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
        barra = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(72), spacing=0)
        etichetta = Label(
            text=self._scrub_testo(getattr(self._media, f"ts_{suffisso}")),
            size_hint_y=None, height=dp(24), font_size=sp(13), halign="left")
        barra.add_widget(etichetta)
        setattr(self, f"scrub_etichetta_{suffisso}", etichetta)
        slider = FineSlider(min=0, max=1, value=0, size_hint_y=None, height=dp(48))
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
            self.status.text = (f"Nessun player disponibile "
                                f"({ultimo_errore() or 'motivo sconosciuto'}): {url}")

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
        corrente = generazione == self._scrub_generazioni.get(suffisso)
        if errore and corrente:
            self.status.text = errore
        elif corrente:
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

    def _occupato(self) -> bool:
        """True se un worker asincrono e' in corso: blocca le azioni che
        toccherebbero i frame in parallelo (transazioni concorrenti)."""
        if self._busy:
            self.status.text = "Attendere: operazione in corso…"
            return True
        return False

    def _placeholder(self, suffisso):
        if self._occupato():
            return
        try:
            self._media.crea_placeholder(suffisso)
        except MediaFlowError as exc:
            self.status.text = str(exc)
            return
        self.status.text = f"Placeholder {suffisso.upper()} impostato come frame."
        self._refresh_frames()
        self._refresh_status()

    def _apri_disegno(self, suffisso):
        """Popup con foglio bianco 5:4 per disegnare il frame a mano."""
        if self._occupato():
            return
        tela = _TelaDisegno()
        area = FloatLayout()
        content = BoxLayout(orientation="vertical", spacing=dp(6))
        popup = Popup(title=f"Disegna frame {suffisso.upper()}", content=content,
                      size_hint=(0.92, 0.88))

        def adatta(*_):
            # il foglio resta 5:4 e il piu' grande possibile nello spazio dato
            lato_lungo = min(area.width, area.height * 5 / 4)
            tela.size = (lato_lungo, lato_lungo * 4 / 5)
            tela.pos = (area.center_x - tela.width / 2, area.center_y - tela.height / 2)

        area.add_widget(tela)
        area.bind(size=adatta, pos=adatta)
        content.add_widget(area)
        comandi = BoxLayout(size_hint_y=None, height=dp(self._ui.target_minimum),
                            spacing=dp(6))
        undo = Button(text="Annulla")
        undo.bind(on_release=lambda _: tela.annulla_tratto())
        clean = Button(text="Pulisci")
        clean.bind(on_release=lambda _: tela.pulisci())
        close = Button(text="Chiudi")
        close.bind(on_release=lambda _: popup.dismiss())
        save = Button(text="Salva")
        save.bind(on_release=lambda _: self._salva_disegno(tela, suffisso, popup))
        for pulsante in (undo, clean, close, save):
            comandi.add_widget(pulsante)
        content.add_widget(comandi)
        popup.open()
        Clock.schedule_once(lambda *_: adatta(), 0)  # geometria definitiva post-open

    def _salva_disegno(self, tela, suffisso, popup):
        if self._occupato():
            return  # popup lasciati aperti: il disegno si recupera e si riprova
        if not tela.tratti:
            self.status.text = "Nessun tratto da salvare: disegna almeno un segno."
            return
        cartella = os.path.dirname(self._media.percorso_anteprima(suffisso))
        disegno = os.path.join(cartella, f"_disegno_{suffisso}.png")
        try:
            os.makedirs(cartella, exist_ok=True)
            tela.esporta_png(disegno)
            self._media.importa_immagine(disegno, suffisso)
        except (MediaFlowError, OSError, ValueError) as exc:
            self.status.text = str(exc)
            return
        finally:
            try:
                os.remove(disegno)
            except OSError:
                pass
        popup.dismiss()
        self.status.text = f"Disegno salvato come frame {suffisso.upper()}."
        self._refresh_frames()
        self._refresh_status()

    def _invalida_scrub(self):
        """Azzera gli scrub pendenti e rende innocui quelli in volo: una
        preview tardiva non deve coprire un frame reale appena impostato
        (placeholder/disegno/import/crop/estrazione). Non serve fermare il
        thread: il callback del worker verra' scartato dal mismatch di
        generazione in ``_scrub_fatto`` (tutto gira sul thread Clock)."""
        for suffisso in ("start", "finish"):
            job = self._scrub_jobs.get(suffisso)
            if job is not None:
                Clock.unschedule(job)
            self._scrub_jobs[suffisso] = None
            self._scrub_pendente[suffisso] = None  # niente recupero a valle
            self._scrub_generazioni[suffisso] = self._scrub_generazioni.get(suffisso, 0) + 1

    def _refresh_frames(self):
        self._invalida_scrub()
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
        if self._menu is not None:
            self._menu.disabled = True
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
        if self._menu is not None:
            self._menu.disabled = False
        self.status.text = errore if errore else ""
        if not errore:
            self._refresh_status()

    def _refresh_status(self):
        self.status.text = (
            f"{self._media.titolo_video or self._media.video_url or 'nessun video'} — "
            f"frame: {'OK' if self._media.pronto() else 'da estrarre'}"
        )
