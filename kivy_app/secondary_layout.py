"""Shared policy for Material dialogs, export surfaces and file actions."""

from __future__ import annotations

from dataclasses import dataclass

from .material import UiProfile


@dataclass(frozen=True)
class SecondaryLayout:
    dialog_max_width: float
    dialog_scrollable: bool
    minimum_target: float
    keyboard_aware: bool


def secondary_layout(profile: UiProfile) -> SecondaryLayout:
    dimensions = profile.tokens.dimensions
    return SecondaryLayout(
        dialog_max_width=dimensions["dialog_max_width"],
        dialog_scrollable=True,
        minimum_target=profile.touch_target,
        keyboard_aware=True,
    )
