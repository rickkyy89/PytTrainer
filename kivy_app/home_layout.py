"""Pure presentation decisions for Home and read-only workout cards."""

from __future__ import annotations

from dataclasses import dataclass

from .material import LayoutPlan, UiProfile


@dataclass(frozen=True)
class ReadonlyCardModel:
    name: str
    repetitions: str
    recovery: str
    explanation: str
    notes: str
    frame_axis: str


def home_plan(profile: UiProfile) -> LayoutPlan:
    return profile.layout("home")


def home_toolbar_rows(profile: UiProfile) -> tuple[tuple[str, ...], ...]:
    """Keep five Home actions reachable without horizontal overflow."""
    actions = ("refresh", "create", "folders", "scale", "text")
    return (actions[:3], actions[3:]) if profile.category == "compact" else (actions,)


def readonly_card(exercise, profile: UiProfile) -> ReadonlyCardModel:
    plan = profile.layout("readonly")
    return ReadonlyCardModel(
        name=exercise.name or "(senza nome)",
        repetitions=exercise.repetitions or "",
        recovery=exercise.recovery or "",
        explanation=exercise.explanation or "",
        notes=exercise.notes or "",
        frame_axis=plan.frames_axis,
    )
