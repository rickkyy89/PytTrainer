"""Pure layout policy for the adaptive editor."""

from __future__ import annotations

from dataclasses import dataclass

from .material import UiProfile


@dataclass(frozen=True)
class EditorLayout:
    accordion: bool
    labels_above: bool
    field_columns: int
    fixed_action_bar: bool
    actions_in_overflow: bool


EDITOR_GLOBAL_ACTIONS = (
    "Importa CSV",
    "Importa da scheda",
    "Genera Google Doc",
    "Impostazioni",
)

EXERCISE_CONTEXT_ACTIONS = ("Su", "Giù", "Vai a…", "Gruppo", "Duplica", "Elimina")


def editor_layout(profile: UiProfile) -> EditorLayout:
    ceiling = 1 if profile.category == "compact" else (2 if profile.category == "medium" else 4)
    return EditorLayout(
        # Cards retain one hierarchy at every width; only their field grid reflows.
        accordion=True,
        labels_above=True,
        field_columns=ceiling,
        fixed_action_bar=True,
        actions_in_overflow=True,
    )


def field_columns(profile: UiProfile, block_width_dp: float) -> int:
    """Single width->columns policy for the short-fields grid of one block.

    The grid lives inside the scrollable column, so its usable width is the
    block width (not the window width); the profile category still caps the
    result so a block never exceeds what the layout plan can host.
    """
    if block_width_dp >= 1200:
        columns = 4
    elif block_width_dp >= 900:
        columns = 3
    elif block_width_dp >= 620:
        columns = 2
    else:
        columns = 1
    return min(columns, editor_layout(profile).field_columns)


def editor_global_actions(*, include_parent: bool = True) -> tuple[str, ...]:
    """Pure ordering policy for the editor app-bar overflow."""
    return EDITOR_GLOBAL_ACTIONS if include_parent else EDITOR_GLOBAL_ACTIONS[:-1]


def exercise_context_actions() -> tuple[str, ...]:
    """Pure, width-independent ordering policy for every exercise overflow."""
    return EXERCISE_CONTEXT_ACTIONS
