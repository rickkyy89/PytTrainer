"""Redesign behavior of the export Kivy screen (app bar, kebab, primary).

Kivy layer of the confirmed Export redesign: exactly one visible primary
action per state, contextual kebab overflow, and the busy protections and
regeneration confirmation preserved.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

kivy = pytest.importorskip("kivy")

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from kivy_app.export_screen import ExportScreen
from kivy_app.material import imposta_pulsanti, pulsanti_correnti

requires_window = pytest.mark.skipif(Window is None, reason="Kivy has no usable window provider")


@pytest.fixture(autouse=True)
def feedback(monkeypatch):
    messaggi = []
    monkeypatch.setattr("kivy_app.export_screen.mostra_snackbar",
                        lambda parent, text, durata=3.0: messaggi.append((parent, text)))
    return messaggi


class ExportStub:
    """DocExportController stand-in; the worker never touches Google/Drive."""

    def __init__(self):
        self.chiamate_genera = []

    def riepilogo(self):
        return SimpleNamespace(titolo="My", pronti=2, totali=3)

    def genera(self, *, force_regenerate=False):
        self.chiamate_genera.append(force_regenerate)
        return {"url": "https://docs/d1", "document_id": "d1",
                "esercizi_inseriti": ["E0", "E1"], "documento_rigenerato": False}

    def progresso(self):
        return (0, 2)


class ThreadStub:
    """Sostituisce threading.Thread nel modulo screen: niente worker reali."""

    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        pass


RISULTATO_OK = {"url": "https://docs/d1", "document_id": "d1",
                "esercizi_inseriti": ["E0"], "documento_rigenerato": False}


def nuova_scheda(on_menu="default", indietro=None):
    export = ExportStub()
    cb = (lambda anchor=None: None) if on_menu == "default" else on_menu
    screen = ExportScreen(export, on_back=indietro or (lambda: None), on_menu=cb)
    screen._run_worker = lambda: None
    screen._menu.pos = (max(Window.width - 60, 0), max(Window.height - 60, 0))
    return screen, export


def voci_menu(menu):
    return [w.text for w in menu.overlay.walk(restrict=True) if isinstance(w, Button)]


def premi_voce(contenitore, testo):
    contenitore = getattr(contenitore, "overlay", contenitore)  # MenuAperto o widget
    for widget in contenitore.walk(restrict=True):
        if isinstance(widget, Button) and widget.text == testo:
            widget.dispatch("on_release")
            return True
    return False


@requires_window
def test_app_bar_uniforme_back_titolo_kebab_e_un_solo_primary(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda()

    header = screen.children[-1]
    etichette = [w.text for w in header.children]
    assert "‹" in etichette and "⋮" in etichette
    assert "Generazione Google Doc" in etichette
    assert [w.text for w in screen.actions.children] == ["Avvia"]  # prima della generazione


@requires_window
def test_dopo_la_generazione_l_unico_primary_e_apri_documento(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda()

    screen._done(RISULTATO_OK)

    assert [w.text for w in screen.actions.children] == ["Apri documento"]
    assert screen.primary.disabled is False


@requires_window
def test_kebab_esporta_voci_contestuali_nell_ordine_del_layout(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda()

    prima = screen._open_export_menu(screen._menu)
    assert voci_menu(prima) == ["Rigenera nuovo", "Impostazioni"]
    prima.dismiss()

    screen._done(RISULTATO_OK)
    dopo = screen._open_export_menu(screen._menu)
    assert voci_menu(dopo) == ["Condividi PDF", "Riprendi", "Rigenera nuovo",
                               "Impostazioni"]
    dopo.dismiss()


@requires_window
def test_senza_on_menu_il_kebab_non_espone_il_menu_globale(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda(on_menu=None)

    menu = screen._open_export_menu(screen._menu)
    assert voci_menu(menu) == ["Rigenera nuovo"]
    menu.dismiss()


@requires_window
def test_rigenera_chiede_conferma_poi_riavvia_con_force(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda()

    menu = screen._open_export_menu(screen._menu)
    assert premi_voce(menu, "Rigenera nuovo")
    popup = next(w for w in Window.children if isinstance(w, Popup))
    assert popup.title == "Rigenerazione"
    assert premi_voce(popup, "Conferma nuovo documento")
    assert screen._force_regenerate is True
    assert screen.busy is True  # il worker (stub) è partito
    assert screen.primary.disabled and screen._back.disabled and screen._menu.disabled

    screen._done(RISULTATO_OK)
    assert screen._force_regenerate is False
    popup.dismiss(animation=False)
    time.sleep(0.3)
    Clock.tick()


@requires_window
def test_l_anello_busy_blocca_kebab_e_back_poi_si_riapre(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    usciti = []
    parent_calls = []
    screen, _ = nuova_scheda(on_menu=lambda anchor=None: parent_calls.append(anchor),
                             indietro=lambda: usciti.append("uscita"))

    screen._start()
    assert screen.busy
    overlays_prima = len(Window.children)
    assert screen._open_export_menu(screen._menu) is None  # kebab inibito dal busy
    assert len(Window.children) == overlays_prima
    screen._back.dispatch("on_release")  # _exit è protetto da busy
    screen._invoke_parent_menu(screen._menu)
    screen._primary_pressed()
    assert usciti == []
    assert parent_calls == []

    screen._done(RISULTATO_OK)
    assert screen.busy is False
    assert not screen._back.disabled and not screen._menu.disabled
    assert screen.primary.text == "Apri documento"


@requires_window
def test_il_menu_genitore_riceve_l_anchor_quando_lo_accetta(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    visti = []
    screen, _ = nuova_scheda(on_menu=lambda anchor=None: visti.append(anchor))
    screen._invoke_parent_menu(screen._menu)
    assert visti == [screen._menu]

    legacy = []
    screen_legacy, _ = nuova_scheda(on_menu=lambda: legacy.append("zero-arg"))
    screen_legacy._invoke_parent_menu(screen_legacy._menu)
    assert legacy == ["zero-arg"]


@requires_window
def test_impostazioni_invoca_il_parent_in_una_sola_selezione(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    visti = []
    screen, _ = nuova_scheda(on_menu=lambda anchor=None: visti.append(anchor))

    menu = screen._open_export_menu(screen._menu)
    assert premi_voce(menu, "Impostazioni")

    assert visti == [screen._menu]


@requires_window
def test_errore_di_generazione_riporta_il_primary_su_avvia_e_apre_popup(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda()

    screen._start()
    screen._failed("Errore: rete")

    assert [w.text for w in screen.actions.children] == ["Avvia"]
    assert screen.primary.disabled is False
    assert screen.progress.text == "Premi Avvia per riprovare."
    popup = next(w for w in Window.children if isinstance(w, Popup))
    testi = [w.text for w in popup.walk(restrict=True) if isinstance(w, Label)]
    assert "Errore: rete" in testi
    popup.dismiss(animation=False)


@requires_window
def test_successo_generazione_usa_snackbar(feedback, monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda()

    screen._done(RISULTATO_OK)

    assert feedback == [(screen, "Documento generato.")]


@requires_window
def test_pdf_worker_conserva_primary_unica_e_blocca_back_menu(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    screen, _ = nuova_scheda()
    screen._done(RISULTATO_OK)

    screen._share_pdf()

    assert screen.busy is True
    assert [w.text for w in screen.actions.children] == ["Apri documento"]
    assert screen.primary.disabled and screen._back.disabled and screen._menu.disabled
    assert screen._open_export_menu(screen._menu) is None
    screen._pdf_failed("Errore PDF: rete")
    assert screen.busy is False
    assert not screen.primary.disabled and not screen._back.disabled and not screen._menu.disabled
    popup = next(w for w in Window.children if isinstance(w, Popup))
    popup.dismiss(animation=False)


@requires_window
@pytest.mark.parametrize("preset,atteso", [("compact", 44), ("standard", 52), ("large", 60)])
def test_export_rispetta_i_tre_preset_pulsanti(preset, atteso, monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    precedente = pulsanti_correnti()
    try:
        imposta_pulsanti(preset)
        screen, _ = nuova_scheda()
        assert screen.header.height == pytest.approx(dp(atteso))
        assert screen._back.width == pytest.approx(dp(atteso))
        assert screen._menu.width == pytest.approx(dp(atteso))
        assert screen.actions.height == pytest.approx(dp(atteso))
    finally:
        imposta_pulsanti(precedente)


@requires_window
def test_export_riapplica_il_preset_quando_torna_da_impostazioni(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    precedente = pulsanti_correnti()
    host = BoxLayout()
    try:
        imposta_pulsanti("compact")
        screen, _ = nuova_scheda()
        host.add_widget(screen)
        assert screen.header.height == pytest.approx(dp(44))
        host.remove_widget(screen)
        imposta_pulsanti("large")
        host.add_widget(screen)
        assert screen.header.height == pytest.approx(dp(60))
        assert screen.actions.height == pytest.approx(dp(60))
    finally:
        imposta_pulsanti(precedente)


@requires_window
def test_errori_launcher_e_document_id_usano_popup(monkeypatch):
    monkeypatch.setattr("kivy_app.export_screen.threading.Thread", ThreadStub)
    monkeypatch.setattr("kivy_app.export_screen.apri_url", lambda url: False)
    monkeypatch.setattr("kivy_app.export_screen.ultimo_errore", lambda: "launcher assente")
    screen, _ = nuova_scheda()
    screen._done(RISULTATO_OK)

    screen._primary_pressed()
    popup = next(w for w in Window.children if isinstance(w, Popup))
    assert popup.title == "Errore"
    popup.dismiss(animation=False)

    screen._document_id = None
    screen._share_pdf()
    popup = next(w for w in Window.children if isinstance(w, Popup))
    assert popup.title == "Errore"
    assert screen.busy is False
    popup.dismiss(animation=False)
