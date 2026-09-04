"""Pure responsive policy for the Video/Frame screen."""

from __future__ import annotations

from dataclasses import dataclass

from .material import UiProfile


@dataclass(frozen=True)
class MediaLayout:
    vertical_page: bool
    frame_axis: str
    target_minimum: float
    keyboard_inset_aware: bool


def media_layout(profile: UiProfile) -> MediaLayout:
    return MediaLayout(
        vertical_page=True,
        frame_axis="vertical" if profile.category == "compact" else "horizontal",
        target_minimum=profile.touch_target,
        keyboard_inset_aware=True,
    )
