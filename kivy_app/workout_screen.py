"""Kivy workout screen: big frames, checkboxes and a recovery timer (ticket 09).

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy. All the
state/countdown logic lives in ``kivy_app.workout.WorkoutSessionController``.
Layout is one-hand friendly: scrolling cards, fixed bottom timer bar with
large targets.
"""

from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.utils import escape_markup
from kivy.core.window import Window
from kivymd.uix.card import MDCard

from .notify import notifica_fine_recupero
from .material import hex_to_rgba, markup_px, profile_for_window
from .workout_layout import workout_layout


def _etichetta(texto, target, delta=48, **kw):
    """Wrapping label: text_size follows the container width, height the texture."""
    kw.setdefault("size_hint_y", None)
    label = Label(text=texto, halign="left", valign="top", markup=True, **kw)
    target.bind(width=lambda _, v, l=label: setattr(l, "text_size", (max(v - delta, 10), None)))
    label.bind(texture_size=lambda l, ts: setattr(l, "height", ts[1]))
    return label


class WorkoutScreen(BoxLayout):
    def __init__(self, session, on_back, notifier=notifica_fine_recupero, on_menu=None):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6))
        self._session = session
        self._on_back = on_back
        self._on_menu = on_menu
        self._notifier = notifier
        self._notified = True
        self._checkboxes: dict[int, CheckBox] = {}
        self._profile = profile_for_window(Window)
        self._ui = workout_layout(self._profile)

        header = BoxLayout(size_hint_y=None, height=dp(self._ui.minimum_target), spacing=dp(8))
        if self._on_menu is not None:
            menu = Button(text="Menu", size_hint_x=None, width=dp(self._ui.minimum_target * 1.7))
            menu.bind(on_release=lambda *_: self._on_menu())
            header.add_widget(menu)
        back = Button(text="< Scheda", size_hint_x=None, width=dp(self._ui.minimum_target * 2))
        back.bind(on_release=lambda *_: self._exit())
        self.progress_label = Label(text=self._progress_text(),
                                    font_size=sp(self._ui.header_font_size))
        reset = Button(text="Azzera", size_hint_x=None, width=dp(self._ui.minimum_target * 2))
        reset.bind(on_release=lambda *_: self._reset())
        header.add_widget(back)
        header.add_widget(self.progress_label)
        header.add_widget(reset)
        self.add_widget(header)

        scroll = ScrollView()
        self.cards = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.cards.bind(minimum_height=self.cards.setter("height"))
        scroll.add_widget(self.cards)
        self.add_widget(scroll)

        bar = BoxLayout(size_hint_y=None, height=dp(max(44, self._ui.minimum_target * 1.8)), spacing=dp(8))
        self.timer_label = Label(text="Recupero: —",
                                 font_size=sp(self._ui.header_font_size * 1.3))
        stop = Button(text="Stop", size_hint_x=None, width=dp(self._ui.minimum_target * 2))
        stop.bind(on_release=lambda *_: self._stop_timer())
        bar.add_widget(self.timer_label)
        bar.add_widget(stop)
        self.add_widget(bar)

        for indice, esercizio in enumerate(self._session.esercizi):
            self.cards.add_widget(self._card(indice, esercizio))

        self._tick_job = Clock.schedule_interval(self._tick, 0.4)

    def apply_text_profile(self):
        """Rebuild only presentation; the session/timer controller is retained."""
        self._profile = profile_for_window(Window)
        self._ui = workout_layout(self._profile)
        self.progress_label.font_size = sp(self._ui.header_font_size)
        self.timer_label.font_size = sp(self._ui.header_font_size * 1.3)
        self.cards.clear_widgets()
        self._checkboxes.clear()
        for indice, esercizio in enumerate(self._session.esercizi):
            self.cards.add_widget(self._card(indice, esercizio))

    # ------------------------------------------------------------- cards

    def _card(self, indice, esercizio):
        colors = self._profile.tokens.colors
        card = MDCard(orientation="vertical", size_hint_y=None, style="filled",
                      theme_bg_color="Custom", md_bg_color=hex_to_rgba(colors["surface_container"]),
                      radius=[dp(self._profile.tokens.dimensions["card_radius"])],
                      spacing=dp(4), padding=dp(6))
        card.bind(minimum_height=card.setter("height"))

        top_height = max(56, self._profile.tokens.typography["title"] * 1.5)
        top = BoxLayout(size_hint_y=None, height=dp(top_height), spacing=dp(6))
        checkbox = CheckBox(size_hint_x=None, width=dp(self._ui.minimum_target),
                            active=self._session.completato(indice))
        checkbox.bind(active=lambda _, active: self._toggle(indice, active))
        self._checkboxes[indice] = checkbox
        top.add_widget(checkbox)
        title_px = markup_px(self._profile, self._profile.tokens.typography["title"])
        body_px = markup_px(self._profile, self._profile.tokens.typography["body"])
        primary = colors["primary"].lstrip("#")
        top.add_widget(_etichetta(
            f"[b][size={title_px}]{escape_markup(str(esercizio.get('nome') or '(senza nome)'))}[/size][/b]  "
            f"[size={body_px}]{escape_markup(str(esercizio.get('ripetizioni') or ''))}[/size]  "
            f"[color={primary}][size={body_px}]{escape_markup(str(esercizio.get('recupero') or ''))}[/size][/color]",
            top, size_hint_x=1))
        card.add_widget(top)

        frames = BoxLayout(orientation=self._ui.frame_axis, size_hint_y=None,
                           height=dp(140 if self._ui.frame_axis == "horizontal" else 280), spacing=dp(4))
        for chiave in ("frame_start", "frame_finish"):
            percorso = esercizio.get(chiave)
            frames.add_widget(Image(source=percorso or "", fit_mode="contain"))
        card.add_widget(frames)

        note = str(esercizio.get("note") or "").strip()
        if note:
            card.add_widget(_etichetta(escape_markup(note), card,
                                        font_size=sp(self._ui.body_font_size),
                                       size_hint_y=None))
        azioni = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(6))
        avvia = Button(text=f"▶ Recupero {indice + 1}")
        avvia.bind(on_release=lambda *_: self._start_timer(indice))
        azioni.add_widget(avvia)
        if str(esercizio.get("video_url") or "").strip():
            video = Button(text="▶ Video", size_hint_x=None, width=dp(120))
            video.bind(on_release=lambda _, e=esercizio: self._play_video(e))
            azioni.add_widget(video)
        card.add_widget(azioni)
        return card

    def _play_video(self, esercizio):
        from .launcher import apri_url
        from .media import url_con_inizio
        url = url_con_inizio(str(esercizio.get("video_url")), esercizio.get("ts_start"))
        if apri_url(url):
            return
        label = Label(text=f"Nessun player disponibile.\n{url}", markup=False,
                      halign="center", valign="middle")
        popup = Popup(title="Video", content=label, size_hint=(0.9, 0.4))
        popup.open()

    # -------------------------------------------------------- interazioni

    def _toggle(self, indice, active):
        current = self._session.completato(indice)
        if active == current:
            return
        self._session.toggle_completato(indice)
        self.progress_label.text = self._progress_text()

    def _reset(self):
        self._session.azzera_sessione()
        for checkbox in self._checkboxes.values():
            checkbox.active = False
        self._notified = True
        self.progress_label.text = self._progress_text()

    def _start_timer(self, indice):
        self._session.avvia_recupero(indice)
        self._notified = False
        self._tick()

    def _stop_timer(self):
        self._session.annulla_recupero()
        self.timer_label.text = "Recupero: —"

    def _tick(self, *_):
        if not self._session.recupero_attivo():
            return
        rimasto = self._session.recupero_rimasto()
        if rimasto == 0:
            if not self._notified:
                self._notified = True
                self._notifier()
            self.timer_label.text = "🔔 RECUPERO FINITO — si riparte"
            return
        self.timer_label.text = f"Recupero {rimasto // 60}:{rimasto % 60:02d}"

    def _progress_text(self):
        return (f"Allenamento — {self._session.conteggio_completati()}"
                f"/{len(self._session.esercizi)} completati")

    def _exit(self):
        self.dispose()
        self._on_back()

    def dispose(self):
        if self._tick_job is not None:
            self._tick_job.cancel()
            self._tick_job = None
