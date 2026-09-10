from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from kivy_app.material import BUTTON_HEIGHTS, ViewportMetrics, adaptive_profile, pulsanti_correnti
from kivy_app.responsive_harness import DEFAULT_SCENARIOS, WidgetBox, run_scenario
from kivy_app.workout_layout import workout_context_actions, workout_layout


def test_workout_compact_is_touch_first_and_stacks_frames():
    layout = workout_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch"), "130"))
    assert layout.frame_axis == "vertical"
    # The confirmed redesign: targets come from the user button preset, not
    # from the platform, so the hierarchy is identical everywhere.
    assert layout.minimum_target == BUTTON_HEIGHTS[pulsanti_correnti()]
    assert layout.body_font_size > 16
    assert layout.fixed_timer_bar


def test_workout_wide_keeps_large_typography_and_side_by_side_frames():
    layout = workout_layout(adaptive_profile(ViewportMetrics(1200, 800)))
    assert layout.frame_axis == "horizontal"
    assert layout.body_font_size == 18
    assert layout.minimum_target == BUTTON_HEIGHTS[pulsanti_correnti()]


def test_workout_target_e_lo_stesso_su_touch_e_pointer():
    touch = workout_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="touch")))
    pointer = workout_layout(adaptive_profile(ViewportMetrics(400, 800, input_mode="pointer")))
    assert touch.minimum_target == pointer.minimum_target


# ------------------------------------------------------- kebab dell'app bar

def test_azzera_vive_solo_nel_kebab_contestuale():
    assert workout_context_actions(include_parent=False) == ("Azzera",)
    assert workout_context_actions() == ("Azzera", "Impostazioni")


def test_stop_e_i_controlli_dei_singoli_esercizi_non_finiscono_in_overflow():
    azioni = workout_context_actions()
    assert not any(parola in " ".join(azioni)
                   for parola in ("Stop", "Recupero", "Video"))


def test_kebab_workout_identico_su_touch_e_pointer():
    touch = workout_context_actions()
    pointer = workout_context_actions()
    assert touch == pointer


# ------------------------------------------- geometria barra senza overflow

# Spaziatura dp(8) tra i widget della barra, alla density 1 degli scenari.
SPAZIO = 8.0


def _barre_workout(profile):
    """App bar + fixed timer bar exactly as WorkoutScreen lays them out."""
    ui = workout_layout(profile)
    target = ui.minimum_target
    larghezza = profile.viewport.width_dp
    altezza = profile.viewport.height_dp
    yield WidgetBox("back", 0, 0, target, target, interactive=True)
    yield WidgetBox("titolo", target + SPAZIO, 0,
                    larghezza - 2 * target - 2 * SPAZIO, target)
    yield WidgetBox("kebab", larghezza - target, 0, target, target, interactive=True)
    barra_h = target
    barra_y = altezza - barra_h
    yield WidgetBox("timer", 0, barra_y, larghezza - 2 * target - SPAZIO, barra_h)
    yield WidgetBox("stop", larghezza - 2 * target, barra_y, 2 * target, barra_h,
                    interactive=True)


@pytest.mark.parametrize("scenario", DEFAULT_SCENARIOS, ids=lambda s: s.name)
def test_app_bar_workout_sta_in_ogni_scenario_senza_overflow(scenario):
    _, _, issues = run_scenario(scenario, _barre_workout)
    assert issues == []
