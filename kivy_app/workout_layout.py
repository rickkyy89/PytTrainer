"""Pure responsive policy for the workout mode."""

from __future__ import annotations

from dataclasses import dataclass

from .material import UiProfile


@dataclass(frozen=True)
class WorkoutLayout:
    frame_axis: str
    minimum_target: float
    header_font_size: float
    body_font_size: float
    fixed_timer_bar: bool


# Ordered contextual kebab for the workout app bar.  "Azzera" moved out of
# the header; "Stop" stays a direct control on the timer bar and the
# per-exercise recovery/video buttons stay on their cards: they are not
# overflow.  The parent (global) entry is appended last, exactly like the
# parent app bar, only when the screen has an on_menu callback.
WORKOUT_CONTEXT_ACTIONS = ("Azzera",)
WORKOUT_PARENT_ACTION = "Impostazioni"


def workout_context_actions(*, include_parent: bool = True) -> tuple[str, ...]:
    """Same minimal kebab hierarchy on every platform and width."""
    return WORKOUT_CONTEXT_ACTIONS + (
        (WORKOUT_PARENT_ACTION,) if include_parent else ())


def workout_layout(profile: UiProfile) -> WorkoutLayout:
    return WorkoutLayout(
        frame_axis="vertical" if profile.category == "compact" else "horizontal",
        minimum_target=profile.touch_target,
        header_font_size=profile.tokens.typography["title"],
        body_font_size=profile.tokens.typography["body"],
        fixed_timer_bar=True,
    )
