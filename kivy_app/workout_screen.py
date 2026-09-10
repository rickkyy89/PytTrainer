"""Kivy workout screen: big frames, checkboxes and a recovery timer (ticket 09).

Imported only from ``kivy_app.main.run`` so pytest never loads Kivy. All the
state/countdown logic lives in ``kivy_app.workout.WorkoutSessionController``.
Layout is one-hand friendly: uniform app bar (back + progress title + kebab
holding "Azzera" and "Impostazioni"), scrolling cards and a fixed bottom
timer bar where "Stop" stays a direct control.
"""

from __future__ import annotations

import inspect

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.image import Image
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.utils import escape_markup
from kivy.core.window import Window
from kivymd.uix.card import MDCard

from .compact_menu import apri_menu
from .notify import notifica_fine_recupero
from .material import hex_to_rgba, markup_px, profile_for_window
from .snackbar import mostra_snackbar
from .workout_layout import workout_context_actions, workout_layout


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

        # Uniform app bar: navigation, live progress as title, one overflow.
        self.header = BoxLayout(size_hint_y=None, height=dp(self._ui.minimum_target),
                                spacing=dp(8))
        self._back = Button(text="‹", size_hint_x=None, width=dp(self._ui.minimum_target))
        self._back.bind(on_release=lambda *_: self._exit())
        self.progress_label = Label(text=self._progress_text(),
                                    font_size=sp(self._ui.header_font_size),
                                    halign="left", valign="middle",
                                    shorten=True, shorten_from="right")
        self.progress_label.bind(width=lambda _, v: setattr(
            self.progress_label, "text_size", (v, self.progress_label.height)))
        self._menu = Button(text="⋮", size_hint_x=None, width=dp(self._ui.minimum_target))
        self._menu.bind(on_release=lambda anchor: self._open_workout_menu(anchor))
        self.header.add_widget(self._back)
        self.header.add_widget(self.progress_label)
        self.header.add_widget(self._menu)
        self.add_widget(self.header)

        scroll = ScrollView()
        self.cards = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.cards.bind(minimum_height=self.cards.setter("height"))
        scroll.add_widget(self.cards)
        self.add_widget(scroll)

        self.timer_bar = BoxLayout(size_hint_y=None, height=dp(self._ui.minimum_target),
                                   spacing=dp(8))
        self.timer_label = Label(text="Recupero: —",
                                 font_size=sp(self._ui.header_font_size * 1.3))
        self._stop = Button(text="Stop", size_hint_x=None,
                            width=dp(self._ui.minimum_target * 2))
        self._stop.bind(on_release=lambda *_: self._stop_timer())
        self.timer_bar.add_widget(self.timer_label)
        self.timer_bar.add_widget(self._stop)
        self.add_widget(self.timer_bar)

        for indice, esercizio in enumerate(self._session.esercizi):
            self.cards.add_widget(self._card(indice, esercizio))

        self._tick_job = Clock.schedule_interval(self._tick, 0.4)
        self._attached_once = False
        self.bind(parent=self._on_parent_changed)

    def apply_text_profile(self):
        """Rebuild only presentation; the session/timer controller is retained."""
        self._profile = profile_for_window(Window)
        self._ui = workout_layout(self._profile)
        target = dp(self._ui.minimum_target)
        self.header.height = target
        self._back.width = target
        self._menu.width = target
        self.timer_bar.height = target
        self._stop.width = target * 2
        self.progress_label.font_size = sp(self._ui.header_font_size)
        self.timer_label.font_size = sp(self._ui.header_font_size * 1.3)
        self.cards.clear_widgets()
        self._checkboxes.clear()
        for indice, esercizio in enumerate(self._session.esercizi):
            self.cards.add_widget(self._card(indice, esercizio))

    def _on_parent_changed(self, _screen, parent):
        """Re-apply settings when this preserved screen returns to the stack."""
        if parent is None:
            return
        if self._attached_once:
            self.apply_text_profile()
        else:
            self._attached_once = True

    # ------------------------------------------------------------- kebab

    def _open_workout_menu(self, anchor):
        """Contextual kebab: session reset and, when wired, the global menu."""
        callbacks = {"Azzera": self._reset,
                     "Impostazioni": lambda: self._invoke_parent_menu(anchor)}
        azioni = workout_context_actions(include_parent=self._on_menu is not None)
        return apri_menu(((label, callbacks[label]) for label in azioni), anchor=anchor)

    def _invoke_parent_menu(self, anchor):
        """Honor both the legacy zero-arg and the anchor-aware parent contract."""
        if self._on_menu is None:
            return None
        try:
            inspect.signature(self._on_menu).bind(anchor)
        except (TypeError, ValueError):
            return self._on_menu()
        return self._on_menu(anchor)

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
        cella = FloatLayout(size_hint_x=None, width=dp(self._ui.minimum_target))
        checkbox = CheckBox(active=self._session.completato(indice))
        checkbox.size_hint = (None, None)
        checkbox.size = (dp(38), dp(38))
        checkbox.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        checkbox.bind(active=lambda _, active: self._toggle(indice, active))
        self._checkboxes[indice] = checkbox
        cella.add_widget(checkbox)
        top.add_widget(cella)
        title_px = markup_px(self._profile, self._profile.tokens.typography["title"])
        body_px = markup_px(self._profile, self._profile.tokens.typography["body"])
        primary = colors["primary"].lstrip("#")
        titolo = _etichetta(
            f"[b][size={title_px}]{escape_markup(str(esercizio.get('nome') or '(senza nome)'))}[/size][/b]  "
            f"[size={body_px}]{escape_markup(str(esercizio.get('ripetizioni') or ''))}[/size]  "
            f"[color={primary}][size={body_px}]{escape_markup(str(esercizio.get('recupero') or ''))}[/size][/color]",
            top, size_hint_x=1)
        top.add_widget(titolo)
        titolo.bind(texture_size=lambda _, ts, box=top, base=top_height:
                    setattr(box, "height", dp(max(base, ts[1] + 8))))
        card.add_widget(top)

        frames = BoxLayout(orientation=self._ui.frame_axis, size_hint_y=None,
                           height=dp(140 if self._ui.frame_axis == "horizontal" else 280), spacing=dp(4))
        for chiave in ("frame_start", "frame_finish"):
            percorso = esercizio.get(chiave)
            immagine = Image(source=percorso or "", fit_mode="contain", nocache=True)
            immagine.bind(on_touch_down=self._tocco_frame(chiave, esercizio))
            frames.add_widget(immagine)
        card.add_widget(frames)

        muted = colors["muted"].lstrip("#")
        spiegazione = str(esercizio.get("spiegazione") or "").strip()
        if spiegazione:
            card.add_widget(_etichetta(escape_markup(spiegazione), card,
                                       font_size=sp(self._ui.body_font_size),
                                       size_hint_y=None))
        note = str(esercizio.get("note") or "").strip()
        if note:
            card.add_widget(_etichetta(
                f"[color={muted}]Note:[/color] {escape_markup(note)}", card,
                font_size=sp(self._ui.body_font_size),
                size_hint_y=None))
        azioni = BoxLayout(size_hint_y=None, height=dp(self._ui.minimum_target),
                           spacing=dp(6))
        avvia = Button(text=f"» Recupero {indice + 1}")
        avvia.bind(on_release=lambda *_: self._start_timer(indice))
        azioni.add_widget(avvia)
        if str(esercizio.get("video_url") or "").strip():
            video = Button(text="» Video", size_hint_x=None, width=dp(120))
            video.bind(on_release=lambda _, e=esercizio: self._play_video(e))
            azioni.add_widget(video)
        card.add_widget(azioni)
        return card

    def _play_video(self, esercizio):
        from .launcher import apri_url, ultimo_errore
        from .media import url_con_inizio
        url = url_con_inizio(str(esercizio.get("video_url")), esercizio.get("ts_start"))
        if apri_url(url):
            return
        label = Label(text=f"Nessun player disponibile.\n{ultimo_errore()}\n{url}",
                      markup=False, halign="center", valign="middle",
                      text_size=(Window.width * 0.8, None))
        popup = Popup(title="Video", content=label, size_hint=(0.9, 0.4))
        popup.open()

    def _tocco_frame(self, chiave, esercizio):
        def on_touch(immagine, tocco):
            if not immagine.collide_point(*tocco.pos):
                return False
            percorso = str(esercizio.get(chiave) or "").strip()
            if not percorso:
                return False
            self._mostra_frame(chiave, percorso)
            return True
        return on_touch

    def _mostra_frame(self, chiave, percorso):
        etichetta = "START" if chiave.endswith("start") else "FINISH"
        contenuto = BoxLayout(orientation="vertical", spacing=dp(6))
        contenuto.add_widget(Image(source=percorso, fit_mode="contain", nocache=True))
        popup = Popup(title=f"Frame {etichetta}", content=contenuto, size_hint=(0.92, 0.85))
        chiudi = Button(text="Chiudi", size_hint_y=None, height=dp(self._ui.minimum_target))
        chiudi.bind(on_release=lambda *_: popup.dismiss())
        contenuto.add_widget(chiudi)
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
        self.timer_label.text = "Recupero: —"
        self.progress_label.text = self._progress_text()
        mostra_snackbar(self, "Allenamento azzerato.")

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
