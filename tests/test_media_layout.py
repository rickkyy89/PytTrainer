"""Responsive policy tests for the redesigned Video/Frame screen.

The confirmed hierarchy is pinned here: app bar kebab holds "URL manuale…"
and the timestamp heuristic (plus the global entry when wired), the video
surface keeps only Play/Cerca/Estrai frame direct, and each START/FINISH
panel keeps Applica/Placeholder direct (no confirmation) with
Disegna/Immagine…/Ripristina in the panel kebab.  Ordering functions are
pure and width-independent, so the same assertions hold on phones and PC.
"""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app.material import BUTTON_HEIGHTS, ViewportMetrics, adaptive_profile, pulsanti_correnti
from kivy_app.media_layout import (
    media_context_actions, media_layout, panel_context_actions,
    panel_direct_actions, video_direct_actions,
)
from kivy_app.responsive_harness import DEFAULT_SCENARIOS, WidgetBox, run_scenario

METRICHE = (
    ViewportMetrics(400, 800, input_mode="touch"),      # compact
    ViewportMetrics(720, 1024, input_mode="touch"),     # medium
    ViewportMetrics(1280, 800, input_mode="pointer"),   # expanded
)


def test_media_stacks_frames_and_keeps_targets_on_compact():
    layout = media_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch")))
    assert layout.vertical_page and layout.frame_axis == "vertical"
    # The confirmed redesign: targets come from the user button preset, not
    # from the platform, so the hierarchy is identical everywhere.
    assert layout.target_minimum == BUTTON_HEIGHTS[pulsanti_correnti()]
    assert layout.keyboard_inset_aware
    assert layout.timestamp_fields_vertical


def test_media_uses_horizontal_frames_on_wide_pointer_view():
    layout = media_layout(adaptive_profile(ViewportMetrics(1200, 800)))
    assert layout.frame_axis == "horizontal"
    assert layout.target_minimum == BUTTON_HEIGHTS[pulsanti_correnti()]
    assert layout.timestamp_fields_vertical


# ------------------------------------------------------- gerarchia d'azioni

def test_solo_play_cerca_ed_estrai_restano_diretti_sul_video():
    assert video_direct_actions() == ("Play", "Cerca", "Estrai frame")


def test_url_manuale_ed_euristica_vivono_nel_kebab_della_app_bar():
    assert media_context_actions(include_parent=False) == ("URL manuale…",
                                                           "Euristica 10%/50%")
    assert media_context_actions() == ("URL manuale…", "Euristica 10%/50%",
                                       "Impostazioni")


def test_azioni_pannello_dirette_senza_conferma():
    # dirette: solo Applica e Placeholder, nessun doppio passo di conferma
    assert panel_direct_actions() == ("Applica", "Placeholder")
    assert panel_context_actions() == ("Disegna", "Immagine…", "Ripristina")
    # gli strumenti del kebab non sono mai anche azioni dirette (e viceversa)
    assert not set(panel_direct_actions()) & set(panel_context_actions())


@pytest.mark.parametrize("metrics", METRICHE)
def test_la_gerarchia_di_azioni_e_identica_su_ogni_profilo(metrics):
    """PC e telefono: stessi livelli d'azione, cambia solo la geometria."""
    media_layout(adaptive_profile(metrics))  # il piano non deve esplodere
    assert video_direct_actions() == ("Play", "Cerca", "Estrai frame")
    assert media_context_actions() == ("URL manuale…", "Euristica 10%/50%",
                                       "Impostazioni")
    assert panel_direct_actions() == ("Applica", "Placeholder")
    assert panel_context_actions() == ("Disegna", "Immagine…", "Ripristina")


# ------------------------------------------- geometria della pagina senza
# --------------------------------------------------------------- overflow

SPAZIO = 4.0  # spacing dp(4) delle righe azioni, alla density 1 degli scenari


def _barra_video(profile):
    """App bar + riga azioni video come MediaScreen le impila (padding dp(10)).

    La pagina e' verticale: app bar in cima, riga status e poi la riga video
    dentro lo scroll. Si modella a partire dal bordo alto del viewport
    (le y del harness crescono verso il basso)."""
    ui = media_layout(profile)
    target = ui.target_minimum
    larghezza = profile.viewport.width_dp - 2 * 10
    altezza = profile.viewport.height_dp
    y_video = ui.header_height + max(32.0, profile.tokens.typography["body"] + 10) + 6
    if y_video + target > altezza:
        pytest.skip("scenario troppo basso per la pagina lunga")
    yield WidgetBox("back", 0, 0, ui.back_width, ui.header_height, interactive=True)
    yield WidgetBox("titolo", ui.back_width + 8, 0,
                    max(larghezza - ui.back_width - ui.kebab_width - 16, 10),
                    ui.header_height)
    yield WidgetBox("kebab-app-bar", larghezza - ui.kebab_width, 0,
                    ui.kebab_width, ui.header_height, interactive=True)
    x = 0.0
    for etichetta in video_direct_actions():
        width = max(80.0, target, len(etichetta) * 9 + 24)
        yield WidgetBox(f"video:{etichetta}", x, y_video, width, target, interactive=True)
        x += width + SPAZIO


@pytest.mark.parametrize("scenario", DEFAULT_SCENARIOS, ids=lambda s: s.name)
def test_barra_video_e_app_bar_non_trabocano_su_ogni_scenario(scenario):
    _profile, _boxes, issues = run_scenario(scenario, _barra_video)
    assert not issues


@pytest.mark.parametrize("metrics", METRICHE)
def test_campi_timestamp_in_verticale_esclusi_dal_calcolo_orizzontale(metrics):
    """Nessuna riga orizzontale di input a larghezza fissa: i campi ts sono
    etichetta + campo pieno impilati, quindi non possono tracimare."""
    ui = media_layout(adaptive_profile(metrics))
    assert ui.timestamp_fields_vertical
