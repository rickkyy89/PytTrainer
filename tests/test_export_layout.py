"""Export app-bar/kebab policy (confirmed redesign); no Kivy is imported."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from kivy_app.export_layout import (
    EXPORT_PARENT_ACTION,
    EXPORT_PRIMARY_GENERATED,
    EXPORT_PRIMARY_READY,
    export_layout,
    export_overflow_actions,
    export_primary_action,
)
from kivy_app.material import ViewportMetrics, adaptive_profile
from kivy_app.responsive_harness import DEFAULT_SCENARIOS, WidgetBox, run_scenario


def test_un_solo_primary_e_adatto_allo_stato():
    assert export_primary_action(generated=False) == EXPORT_PRIMARY_READY == "Avvia"
    assert export_primary_action(generated=True) == EXPORT_PRIMARY_GENERATED == "Apri documento"


def test_kebab_prima_della_generazione_ha_solo_rigenera_nuovo():
    assert export_overflow_actions(generated=False, include_parent=False) == ("Rigenera nuovo",)
    assert export_overflow_actions(generated=False) == ("Rigenera nuovo", "Impostazioni")
    assert EXPORT_PARENT_ACTION == "Impostazioni"


def test_kebab_dopo_la_generazione_aggiunge_condividi_e_riprendi_in_ordine():
    assert export_overflow_actions(generated=True, include_parent=False) == (
        "Condividi PDF", "Riprendi", "Rigenera nuovo")
    assert export_overflow_actions(generated=True)[-1] == EXPORT_PARENT_ACTION


def test_il_primary_non_si_ripete_mai_nel_kebab():
    for generated in (False, True):
        assert export_primary_action(generated=generated) not in \
            export_overflow_actions(generated=generated)


def test_gerarchia_identica_su_touch_e_pointer():
    phone = export_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch")))
    desktop = export_layout(adaptive_profile(ViewportMetrics(1280, 800)))
    for ui in (phone, desktop):
        assert ui.back_width == ui.kebab_width == ui.minimum_target
        assert ui.header_height == ui.primary_height == ui.minimum_target
        assert ui.title_min_width > 0


@pytest.mark.parametrize("generated", [False, True])
def test_overflow_non_cambia_con_la_larghezza(generated):
    profili = [adaptive_profile(ViewportMetrics(w, h, input_mode=m))
               for w, h, m in ((400, 800, "touch"), (720, 1024, "touch"), (1280, 800, "pointer"))]
    azioni = [export_overflow_actions(generated=generated) for _ in profili]
    assert all(a == azioni[0] for a in azioni)


# Spaziatura dp(8) tra i widget della barra, alla density 1 degli scenari.
SPAZIO = 8.0


def _barre_export(profile):
    """App bar + primary row exactly as ExportScreen lays them out."""
    ui = export_layout(profile)
    larghezza = profile.viewport.width_dp
    yield WidgetBox("back", 0, 0, ui.back_width, ui.header_height, interactive=True)
    yield WidgetBox("titolo", ui.back_width + SPAZIO, 0,
                    ui.title_min_width, ui.header_height)
    yield WidgetBox("kebab", larghezza - ui.kebab_width, 0,
                    ui.kebab_width, ui.header_height, interactive=True)
    yield WidgetBox("primary", 0, ui.header_height + SPAZIO,
                    larghezza, ui.primary_height, interactive=True)


@pytest.mark.parametrize("scenario", DEFAULT_SCENARIOS, ids=lambda s: s.name)
def test_app_bar_export_sta_in_ogni_scenario_senza_overflow(scenario):
    _, _, issues = run_scenario(scenario, _barre_export)
    assert issues == []
