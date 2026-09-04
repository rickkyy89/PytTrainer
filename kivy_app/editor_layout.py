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


def editor_layout(profile: UiProfile) -> EditorLayout:
    compact = profile.category == "compact"
    return EditorLayout(
        accordion=compact,
        labels_above=compact,
        field_columns=1 if compact else 2,
        fixed_action_bar=True,
        actions_in_overflow=True,
    )
