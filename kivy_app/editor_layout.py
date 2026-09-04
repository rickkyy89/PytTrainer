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
    ceiling = 1 if compact else (2 if profile.category == "medium" else 4)
    return EditorLayout(
        accordion=compact,
        labels_above=compact,
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
