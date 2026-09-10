"""Pure presentation decisions for Home and read-only workout cards."""

from __future__ import annotations

from dataclasses import dataclass

from .material import LayoutPlan, UiProfile


HOME_MENU_LABELS = (
    "Scheda con AI", "Apri locale", "Apri cartella Drive", "Impostazioni",
)


@dataclass(frozen=True)
class ReadonlyCardModel:
    name: str
    repetitions: str
    recovery: str
    explanation: str
    notes: str
    frame_axis: str


def etichetta_recupero(valore: str) -> str:
    """Return the user-facing recovery label, without adding empty metadata."""
    return f"Recupero: {valore}" if valore else ""


def home_plan(profile: UiProfile) -> LayoutPlan:
    return profile.layout("home")


def home_toolbar_rows(profile: UiProfile) -> tuple[tuple[str, ...], ...]:
    """The fixed Home action bar is intentionally identical at every width."""
    del profile
    return (("refresh", "create"),)


def abbrevia_id(folder_id: str, visible: int = 6) -> str:
    """Readable but still distinguishable Drive ID for the settings list."""
    if len(folder_id) <= visible * 2 + 1:
        return folder_id
    return f"{folder_id[:visible]}…{folder_id[-visible:]}"


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
