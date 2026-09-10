"""Kivy screen for choosing the video and frames of one exercise (ticket 07).

Functional parity with the Streamlit "Video & Frame" tab: search results with
title/duration and selection, manual URL override, timestamp fields with the
10%/50% heuristic proposal, extraction through the platform backend, frame
previews, per-side percentage crop with ``*_orig.jpg`` backup and restore,
user image import, placeholder frames and a 5:4 free-hand drawing popup for
START/FINISH.

Layout (redesign confermato): app bar with back + title + kebab contestuale
(il kebab schermo ospita "URL manuale…" e "Euristica 10%/50%", più la voce
che invoca il menu globale ``on_menu``); azioni video dirette Play/Cerca/
Estrai frame; campi timestamp impilati in verticale (niente overflow
orizzontale sui telefoni, identica gerarchia di azioni su PC); nei pannelli
START/FINISH restano diretti solo Applica e Placeholder (senza conferma),
mentre Disegna/Immagine…/Ripristina vivono nel kebab del pannello. La
gerarchia d'azione è definita in ``media_layout`` ed è uguale su ogni
profilo. Il corpo della pagina viene ricostruito quando resize/rotazione
cambiano il piano responsive.

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy.
"""

from __future__ import annotations

import inspect
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
from .compact_menu import apri_menu
from .snackbar import mostra_snackbar
from .media_layout import (
    media_context_actions, media_layout, panel_context_actions,
    panel_direct_actions, video_direct_actions,
)


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
        # Settings applies to newly opened canvases without coupling it to a bundle.
        from .material import spessore_penna_corrente
        self.SPESSORE_EXPORT = spessore_penna_corrente()
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
        self._layout_key = self._chiave_layout()
        # stato dei worker/share: creato una sola volta, sopravvive alla
        # ricostruzione del corpo durante i reflow del piano responsive
        self._scrub_jobs: dict[str, object] = {}
        self._scrub_generazioni: dict[str, int] = {}
        self._scrub_pendente: dict[str, float] = {}
        self._scrub_in_corso: dict[str, float] = {}
        self._scrub_in_volo: set[str] = set()
        self._scrub_slider: dict[str, Slider] = {}
        self._preview_jobs: dict[str, object] = {}
        self._crop_sliders: dict[str, dict[str, Slider]] = {}
        self._mutating_controls: list[Widget] = []
        self._result_controls: list[Widget] = []
        self._syncing = False
        self._reflowing = False
        self._reflow_job = None
        self._error_popup = None

        # Uniform app bar: navigation, title and one contextual overflow
        # (identical to the editor/export/workout app-bar contract).
        tokens = self._profile.tokens
        bar = BoxLayout(size_hint_y=None, height=dp(self._ui.header_height),
                        spacing=dp(8))
        self._back = Button(text="‹", size_hint_x=None, width=dp(self._ui.back_width))
        self._back.bind(on_release=lambda *_: self._exit())
        self.titolo = Label(text="Video & Frame",
                            font_size=sp(tokens.typography["section"]),
                            halign="left", valign="middle",
                            shorten=True, shorten_from="right")
        self.titolo.bind(
            width=lambda _, v: setattr(self.titolo, "text_size", (v, self.titolo.height)))
        self._menu = Button(text="⋮", size_hint_x=None, width=dp(self._ui.kebab_width))
        self._menu.bind(on_release=lambda anchor: self._open_media_menu(anchor))
        bar.add_widget(self._back)
        bar.add_widget(self.titolo)
        bar.add_widget(self._menu)
        self.add_widget(bar)

        self.status = Label(text="", size_hint_y=None,
                            height=dp(max(32, tokens.typography["body"] + 10)),
                            halign="left", valign="middle",
                            shorten=True, shorten_from="right")
        self.status.bind(
            width=lambda _, v: setattr(self.status, "text_size", (v, self.status.height)))
        self.add_widget(self.status)

        body = ScrollView()
        self._scroll = body
        self.column = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.column.bind(minimum_height=self.column.setter("height"))
        body.add_widget(self.column)
        self.add_widget(body)

        self._build_video_section()
        self._build_frame_section()
        self._refresh_status()
        # rotazione/resize: se il piano responsive cambia, si riflowa il corpo
        self.bind(size=self._on_size)
        if self._media.video_url and self._media.durata is None:
            # video proveniente dal manifest: la pista scrub non conosce la
            # durata, va risolta in background prima di poterla usare
            self._run_async(self._do_durata)

    # ------------------------------------------------------- menu e reflow

    @property
    def busy(self):
        """Reliable public busy state consumed by the application close guard."""
        return self._busy

    def _exit(self):
        if self._occupato():
            return
        self._on_back()

    def _open_media_menu(self, anchor):
        """Kebab della app bar: azioni schermo + accesso al menu globale."""
        if self._occupato():
            return None
        callbacks = {
            "URL manuale…": self._manual_url_popup,
            "Euristica 10%/50%": self._apply_heuristic,
        }
        if self._on_menu is not None:
            callbacks["Impostazioni"] = lambda: self._open_parent_settings(anchor)
        return self._open_local_menu(
            tuple((label, callbacks[label])
                  for label in media_context_actions(
                      include_parent=self._on_menu is not None)),
            anchor=anchor)

    def _open_panel_menu(self, suffisso, anchor):
        """Kebab del pannello START/FINISH: Disegna, Immagine…, Ripristina."""
        if self._occupato():
            return None
        callbacks = {
            "Disegna": lambda: self._apri_disegno(suffisso),
            "Immagine…": lambda: self._import_image(suffisso),
            "Ripristina": lambda: self._restore(suffisso),
        }
        return self._open_local_menu(
            tuple((label, callbacks[label]) for label in panel_context_actions()),
            anchor=anchor)

    def _open_local_menu(self, actions, anchor):
        """Open a local kebab and apply the exact 44/52/60 control preset.

        Shared ``apri_menu`` historically floors rows at 48dp. Media owns the
        stricter confirmed contract, so its menu buttons are retuned after
        construction without changing common infrastructure.
        """
        menu = apri_menu(actions, anchor=anchor)
        root = getattr(menu, "overlay", menu)
        walk = getattr(root, "walk", None)
        if walk is None:
            return menu
        for widget in walk(restrict=True):
            if isinstance(widget, Button):
                widget.height = dp(self._ui.target_minimum)
        return menu

    def _open_parent_settings(self, anchor):
        """Open Settings in one selection with the current main callback.

        Main passes its bound ``apri_menu`` method. Its owner also exposes
        ``show_settings``; calling that public callback avoids a redundant
        one-item parent menu. Other embedders retain the legacy menu fallback.
        """
        owner = getattr(self._on_menu, "__self__", None)
        callback = getattr(owner, "show_settings", None)
        if callable(callback):
            return callback()
        return self._invoke_parent_menu(anchor)

    def _invoke_parent_menu(self, anchor):
        """Honor both the legacy zero-arg and the anchor-aware parent contract."""
        if self._on_menu is None:
            return None
        try:
            inspect.signature(self._on_menu).bind(anchor)
        except (TypeError, ValueError):
            return self._on_menu()
        return self._on_menu(anchor)

    def _chiave_layout(self):
        """Tutto ciò che, cambiando, impone la ricostruzione del corpo."""
        profilo = profile_for_window(Window)
        piano = media_layout(profilo)
        return (piano, profilo.tokens.dimensions["frame_min_height"],
                profilo.tokens.typography["label"])

    def _on_size(self, *_):
        if self.width <= 0 or self.height <= 0:
            return
        chiave = self._chiave_layout()
        if chiave == self._layout_key:
            if self._reflow_job is not None:
                # la finestra e' tornata al piano corrente: nessun riflow
                Clock.unschedule(self._reflow_job)
                self._reflow_job = None
            return
        if self._reflow_job is not None:
            Clock.unschedule(self._reflow_job)
        # debounce: il drag della finestra non ricostruisce a ogni frame
        self._reflow_job = Clock.schedule_once(self._riflow, 0.2)

    def _riflow(self, *_):
        """Ricostruisce il corpo della pagina sul nuovo piano responsive."""
        self._reflow_job = None
        chiave = self._chiave_layout()  # ri-legge la finestra: il piano puo'
        if chiave == self._layout_key:  # essere cambiato durante il debounce
            return
        state = self._capture_reflow_state()
        committed = self._commit_timestamp_fields(allow_busy=True)
        self._layout_key = chiave
        self._reflowing = True
        self._invalida_scrub()
        for job in self._preview_jobs.values():
            if job is not None:
                Clock.unschedule(job)
        self._preview_jobs.clear()
        self._profile = profile_for_window(Window)
        self._ui = media_layout(self._profile)
        self.column.clear_widgets()
        self._mutating_controls = []
        self._result_controls = []
        self._crop_sliders = {}
        self._build_video_section()
        self._build_frame_section()
        self._sync_video_widgets()
        for suffisso, valori in state["crop"].items():
            for lato, valore in valori.items():
                self._crop_sliders[suffisso][lato].value = valore
        if not committed:
            self.ts_start.text = state["timestamp"]["start"]
            self.ts_finish.text = state["timestamp"]["finish"]
        self._reflowing = False
        self._set_mutating_controls_disabled(self._busy)
        if state["focused"]:
            Clock.schedule_once(
                lambda *_: setattr(getattr(self, f"ts_{state['focused']}"), "focus", True), 0)

    def _capture_reflow_state(self):
        return {
            "timestamp": {"start": self.ts_start.text, "finish": self.ts_finish.text},
            "focused": "start" if self.ts_start.focus else "finish" if self.ts_finish.focus else None,
            "crop": {
                suffisso: {lato: float(slider.value) for lato, slider in sliders.items()}
                for suffisso, sliders in self._crop_sliders.items()
            },
        }

    def _do_durata(self):
        self._media.assicura_durata()
        Clock.schedule_once(lambda *_: self._sync_scrub_sliders(), 0)

    # ------------------------------------------------------------- video

    def _build_video_section(self):
        video_line = BoxLayout(size_hint_y=None, height=dp(self._ui.target_minimum),
                               spacing=dp(4))
        self.video_label = Label(text=f"Video: {self._media.video_url or 'nessuno'}",
                                 halign="left", valign="middle",
                                 shorten=True, shorten_from="right")
        self.video_label.bind(
            width=lambda _, v: setattr(self.video_label, "text_size", (v, self.video_label.height)))
        video_line.add_widget(self.video_label)
        azioni_video = {
            "Play": self._play,
            "Cerca": lambda: self._run_async(self._do_search),
            "Estrai frame": lambda: self._run_async(self._do_extract),
        }
        for etichetta in video_direct_actions():
            # larghezza che cresce col testo: a target grandi "Estrai frame"
            # non deve risultare tagliato
            pulsante = Button(text=etichetta, size_hint_x=None,
                              width=dp(max(80, self._ui.target_minimum,
                                           len(etichetta) * 9 + 24)))
            pulsante.bind(on_release=lambda _, az=etichetta: azioni_video[az]())
            video_line.add_widget(pulsante)
            if etichetta != "Play":
                self._register_mutating_control(pulsante)
        self.column.add_widget(video_line)

        # campi timestamp in verticale: etichetta sopra campo a piena
        # larghezza, nessuna riga orizzontale che tracimi sullo smartphone
        campo_h = dp(self._ui.target_minimum)
        etichetta_h = dp(max(22, self._profile.tokens.typography["label"] + 4))
        ts_box = BoxLayout(orientation="vertical", size_hint_y=None,
                           height=etichetta_h * 2 + campo_h * 2 + dp(12) + dp(12),
                           spacing=dp(4), padding=[dp(6), dp(8)])
        self._tinta_riquadro(ts_box)
        self.ts_start = TextInput(text=self._ts_text(self._media.ts_start),
                                  multiline=False, size_hint_y=None, height=campo_h)
        self.ts_start.bind(focus=self._ts_handler("ts_start", self.ts_start))
        self.ts_finish = TextInput(text=self._ts_text(self._media.ts_finish),
                                   multiline=False, size_hint_y=None, height=campo_h)
        self.ts_finish.bind(focus=self._ts_handler("ts_finish", self.ts_finish))
        self._register_mutating_control(self.ts_start)
        self._register_mutating_control(self.ts_finish)
        for testo, campo in (("Start s", self.ts_start), ("Finish s", self.ts_finish)):
            etichetta = Label(text=testo, size_hint_y=None, height=etichetta_h,
                              halign="left", valign="bottom")
            etichetta.bind(
                width=lambda _, v, l=etichetta: setattr(l, "text_size", (v, l.height)))
            ts_box.add_widget(etichetta)
            ts_box.add_widget(campo)
        self.column.add_widget(ts_box)

        self.results = BoxLayout(orientation="vertical", spacing=4, size_hint_y=None)
        self.results.bind(minimum_height=self.results.setter("height"))
        self.column.add_widget(self.results)
        self._render_results()

    def _ts_text(self, valore) -> str:
        return "" if valore is None else f"{float(valore):.1f}"

    def _ts_handler(self, chiave, campo):
        def on_focus(instance, focused):
            if focused or self._reflowing:
                return
            if self._occupato() or not self._commit_timestamp_fields():
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
        if self._occupato():
            return
        if not self._media.video_url:
            self._mostra_errore("Seleziona prima un video.")
            return
        self._run_async(self._do_heuristic,
                        success="Timestamp aggiornati con l'euristica 10%/50%.")

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
        for control in self._result_controls:
            if control in self._mutating_controls:
                self._mutating_controls.remove(control)
        self._result_controls = []
        self.results.clear_widgets()
        for indice, scelta in enumerate(self._media.scelte):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            info = Button(text=f"{indice + 1}. {scelta.title[:60]} ({_formatta_durata(scelta.duration)})",
                          halign="left", valign="middle", shorten=True)
            info.bind(width=lambda _, v, b=info: setattr(b, "text_size", (max(v - dp(20), 10), b.height)),
                      height=lambda _, h, b=info: setattr(b, "text_size", (max(b.width - dp(20), 10), h)))
            info.bind(on_release=lambda _, i=indice: self._run_async(lambda: self._choose(i)))
            self._register_mutating_control(info, result=True)
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
        if self._occupato():
            return None
        input_url = TextInput(hint_text="https://www.youtube.com/watch?v=...",
                              multiline=False)
        buttons = BoxLayout(size_hint_y=None, height=dp(self._ui.target_minimum),
                            spacing=dp(8))
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
        if self._occupato():
            return
        popup.dismiss()
        try:
            self._media.url_manuale(url)
        except MediaFlowError as exc:
            self._mostra_errore(exc)
            return
        self._sync_video_widgets()
        self._refresh_status()
        self._mostra_info("URL video aggiornato.")

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
        # UNA sola riga di azioni dirette (Applica, Placeholder + kebab):
        # Disegna/Immagine…/Ripristina non ingombrano più il pannello,
        # vivono nel kebab contestuale ancorato al pulsante ⋮
        azioni_h = self._ui.target_minimum + 4
        # altezza di UN pannello START/FINISH completo (preview + scrub + crop
        # + azioni, con un po' di margine per gli spacing interni del pannello)
        pannello_h = anteprima_min + scrub_h + lato_h + azioni_h + 24
        # in compact i due pannelli si impilano (asse verticale): la riga deve
        # contenerne DUE piu' lo spacing, non dividere l'altezza di uno
        altezza_riga = pannello_h * 2 + 8 if self._ui.frame_axis == "vertical" else pannello_h
        self.frames_row = BoxLayout(
            orientation=self._ui.frame_axis, size_hint_y=None,
            height=dp(altezza_riga), spacing=dp(8))
        # i dizionari di stato dei worker nascono in __init__ e sopravvivono
        # ai reflow: qui si registrano solo i nuovi slider del corpo
        self._scrub_slider = {}
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
                self._register_mutating_control(slider)
                box.add_widget(slider)
                sliders[lato] = slider
                lato_line.add_widget(box)
            for slider in sliders.values():
                slider.bind(on_value=self._preview_handler(suffisso, sliders))
            self._crop_sliders[suffisso] = sliders
            panel.add_widget(lato_line)
            azioni_pannello = {
                "Applica": lambda sl=sliders, s=suffisso: self._apply_crop(s, sl),
                "Placeholder": lambda s=suffisso: self._placeholder(s),
            }
            azioni_riga = BoxLayout(size_hint_y=None,
                                    height=dp(self._ui.target_minimum), spacing=dp(4))
            for etichetta in panel_direct_actions():
                pulsante = Button(text=etichetta)
                pulsante.bind(on_release=lambda _, az=etichetta: azioni_pannello[az]())
                azioni_riga.add_widget(pulsante)
                self._register_mutating_control(pulsante)
            kebab = Button(text="⋮", size_hint_x=None,
                           width=dp(self._ui.target_minimum))
            kebab.bind(on_release=lambda anchor, s=suffisso:
                       self._open_panel_menu(s, anchor))
            self._register_mutating_control(kebab)
            azioni_riga.add_widget(kebab)
            panel.add_widget(azioni_riga)
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
        self._register_mutating_control(slider)
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
            self._mostra_errore(exc)
            return
        if apri_url(url):
            self._mostra_info("Video aperto dal punto START.")
        else:
            self._mostra_errore(f"Nessun player disponibile "
                                f"({ultimo_errore() or 'motivo sconosciuto'}): {url}")

    def _scrub_testo(self, valore) -> str:
        durata = self._media.durata
        base = f"Tempo: {'' if valore is None else f'{float(valore):.1f}'} s"
        return f"{base}   (video: {_formatta_durata(durata) if durata else 'durata n/d'})"

    def _scrub_handler(self, suffisso, slider):
        def on_value(*_):
            getattr(self, f"scrub_etichetta_{suffisso}").text = self._scrub_testo(slider.value)
            if (self._syncing or self._reflowing or self._busy or slider.disabled
                    or not self._media.video_url):
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
            self._mostra_errore(errore)
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
        if self._occupato():
            return
        if slider.disabled or not self._media.video_url:
            return
        if touch is not None and not slider.collide_point(*touch.pos):
            return  # tocco nato altrove (scroll della pagina): non committare
        try:
            self._media.imposta_timestamp(**{f"ts_{suffisso}": float(slider.value)})
        except MediaFlowError as exc:
            self._mostra_errore(exc)
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
            if self._reflowing or self._busy:
                return
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
            self._mostra_errore(exc)
            return
        preview.source = anteprima
        preview.reload()

    def _apply_crop(self, suffisso, sliders):
        if self._occupato():
            return
        try:
            self._media.ritaglia(suffisso, sliders["sinistra"].value,
                                 sliders["alto"].value, sliders["destra"].value,
                                 sliders["basso"].value)
        except MediaFlowError as exc:
            self._mostra_errore(exc)
            return
        except ValueError as exc:  # vincoli percentuali di box_ritaglio
            self._mostra_errore(exc)
            return
        for slider in sliders.values():
            slider.value = 0
        self._refresh_frames()
        self._mostra_info("Ritaglio applicato.")

    def _restore(self, suffisso):
        if self._occupato():
            return
        try:
            self._media.ripristina(suffisso)
        except MediaFlowError as exc:
            self._mostra_errore(exc)
            return
        self._refresh_frames()
        self._mostra_info("Originale ripristinato.")

    def _import_image(self, suffisso):
        if self._occupato():
            return
        def on_result(percorso):
            if not percorso:
                return
            if self._occupato():
                return
            try:
                self._media.importa_immagine(percorso, suffisso)
            except MediaFlowError as exc:
                Clock.schedule_once(lambda _, testo=str(exc): self._mostra_errore(testo), 0)
                return
            Clock.schedule_once(lambda *_: (self._refresh_frames(),
                                            self._refresh_status(),
                                            self._mostra_info("Immagine importata.")), 0)
        choose_file(on_result, title=f"Scegli immagine {suffisso.upper()}",
                    patterns=[("Immagini", ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"])])

    def _occupato(self) -> bool:
        """True se un worker asincrono e' in corso: blocca le azioni che
        toccherebbero i frame in parallelo (transazioni concorrenti)."""
        if self._busy:
            self._mostra_info("Attendere: operazione in corso…")
            return True
        return False

    def _placeholder(self, suffisso):
        if self._occupato():
            return
        try:
            self._media.crea_placeholder(suffisso)
        except MediaFlowError as exc:
            self._mostra_errore(exc)
            return
        self._refresh_frames()
        self._refresh_status()
        self._mostra_info(f"Placeholder {suffisso.upper()} impostato.")

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
            self._mostra_errore("Nessun tratto da salvare: disegna almeno un segno.")
            return
        cartella = os.path.dirname(self._media.percorso_anteprima(suffisso))
        disegno = os.path.join(cartella, f"_disegno_{suffisso}.png")
        try:
            os.makedirs(cartella, exist_ok=True)
            tela.esporta_png(disegno)
            self._media.importa_immagine(disegno, suffisso)
        except (MediaFlowError, OSError, ValueError) as exc:
            self._mostra_errore(exc)
            return
        finally:
            try:
                os.remove(disegno)
            except OSError:
                pass
        popup.dismiss()
        self._refresh_frames()
        self._refresh_status()
        self._mostra_info(f"Disegno salvato come frame {suffisso.upper()}.")

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

    # --------------------------------------------------------- UI contract

    def _register_mutating_control(self, control, *, result=False):
        """Track every control able to mutate media or start mutable work."""
        self._mutating_controls.append(control)
        if result:
            self._result_controls.append(control)
        control.disabled = self._busy
        return control

    def _set_mutating_controls_disabled(self, disabled):
        for control in self._mutating_controls:
            control.disabled = bool(disabled)

    def _commit_timestamp_fields(self, *, allow_busy=False):
        """Atomically validate and commit visible timestamps.

        Parsing both fields before calling the controller avoids a partial
        START update when FINISH is invalid. Empty fields retain the model
        value, matching the previous focus-loss behavior.
        """
        if self._busy and not allow_busy:
            self._mostra_info("Attendere: operazione in corso…")
            return False
        updates = {}
        for suffisso, campo in (("start", self.ts_start), ("finish", self.ts_finish)):
            testo = campo.text.strip().replace(",", ".")
            if not testo:
                continue
            try:
                valore = float(testo)
            except ValueError:
                self._mostra_errore(f"Timestamp non numerico: {testo}")
                return False
            if valore < 0:
                self._mostra_errore(f"Timestamp ts_{suffisso} non valido: {valore}.")
                return False
            corrente = getattr(self._media, f"ts_{suffisso}")
            if corrente is None or abs(float(corrente) - valore) > 0.0001:
                updates[f"ts_{suffisso}"] = valore
        if not updates:
            return True
        try:
            self._media.imposta_timestamp(**updates)
        except MediaFlowError as exc:
            self._mostra_errore(exc)
            return False
        return True

    def _mostra_info(self, testo):
        return mostra_snackbar(self, str(testo))

    def _mostra_errore(self, errore):
        """Errors are modal by contract; success/info use snackbars."""
        if self._error_popup is not None:
            self._error_popup.dismiss(animation=False)
        contenuto = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        messaggio = Label(text=str(errore), halign="left", valign="middle")
        messaggio.bind(width=lambda _, value: setattr(
            messaggio, "text_size", (max(value - dp(16), dp(40)), None)))
        chiudi = Button(text="Chiudi", size_hint_y=None,
                        height=dp(self._ui.target_minimum))
        popup = Popup(title="Errore", content=contenuto, size_hint=(0.88, 0.38))
        chiudi.bind(on_release=lambda *_: popup.dismiss())
        popup.bind(on_dismiss=lambda *_: setattr(self, "_error_popup", None))
        contenuto.add_widget(messaggio)
        contenuto.add_widget(chiudi)
        self._error_popup = popup
        popup.open()
        return popup

    # ------------------------------------------------------------- async

    def _run_async(self, operation, *, success=None):
        if self._busy:
            self._mostra_info("Attendere: operazione in corso…")
            return
        if not self._commit_timestamp_fields():
            return
        self._busy = True
        self._back.disabled = True  # niente ritorno (e niente Salva) durante il worker
        self._menu.disabled = True  # il kebab schermo/globale segue il back
        self._set_mutating_controls_disabled(True)
        self.status.text = "Elaboro…"

        def worker():
            try:
                operation()
                Clock.schedule_once(lambda *_: self._finish_async(None, success), 0)
            except Exception as exc:
                # eccoti il messaggio materializzato SUBITO: fuori dal blocco
                # except il nome exc verrebbe cancellato e la lambda romperebbe.
                testo = str(exc) if isinstance(exc, MediaFlowError) else f"Errore imprevisto: {exc}"
                Clock.schedule_once(
                    lambda _, testo=testo: self._finish_async(testo, None), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_async(self, errore, success=None):
        self._busy = False
        self._back.disabled = False
        self._menu.disabled = False
        self._set_mutating_controls_disabled(False)
        self._refresh_status()
        if errore:
            self._mostra_errore(errore)
        elif success:
            self._mostra_info(success)

    def _refresh_status(self):
        self.status.text = (
            f"{self._media.titolo_video or self._media.video_url or 'nessun video'} — "
            f"frame: {'OK' if self._media.pronto() else 'da estrarre'}"
        )
