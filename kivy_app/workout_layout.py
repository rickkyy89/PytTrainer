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


def workout_layout(profile: UiProfile) -> WorkoutLayout:
    return WorkoutLayout(
        frame_axis="vertical" if profile.category == "compact" else "horizontal",
        minimum_target=profile.touch_target,
        header_font_size=profile.tokens.typography["title"],
        body_font_size=profile.tokens.typography["body"],
        fixed_timer_bar=True,
    )
