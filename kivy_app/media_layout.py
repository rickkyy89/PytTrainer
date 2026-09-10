"""Pure responsive policy for the Video/Frame screen.

Like the other layout modules this one has no Kivy import: the screen
translates these numbers into widgets, while tests verify the confirmed
action hierarchy — app bar kebab holding "URL manuale…" and the timestamp
heuristic, direct video actions (Play/Cerca/Estrai frame), per-panel direct
actions without confirmation (Applica/Placeholder) and the panel kebab
holding Disegna/Immagine…/Ripristina.  The ordering functions are pure and
width-independent on purpose: phones and desktops get the SAME hierarchy and
only the geometry reflows.  Timestamp fields always stack vertically so no
horizontal row of fixed-width inputs can overflow a narrow viewport.
"""

from __future__ import annotations

from dataclasses import dataclass

from .material import UiProfile

# Direct video actions on the page; URL manuale and the heuristic are NOT
# here, they live in the app-bar kebab below.
VIDEO_DIRECT_ACTIONS = ("Play", "Cerca", "Estrai frame")

# Ordered contextual kebab of the app bar (screen actions +, appended last
# and only when wired, the global menu entry — same contract as the editor,
# export and workout app bars).
MEDIA_CONTEXT_ACTIONS = ("URL manuale…", "Euristica 10%/50%")
MEDIA_PARENT_ACTION = "Impostazioni"

# Per START/FINISH panel: the direct row carries only the two no-confirmation
# actions; every other frame tool hangs in the panel kebab.
PANEL_DIRECT_ACTIONS = ("Applica", "Placeholder")
PANEL_CONTEXT_ACTIONS = ("Disegna", "Immagine…", "Ripristina")


@dataclass(frozen=True)
class MediaLayout:
    vertical_page: bool
    frame_axis: str
    target_minimum: float
    keyboard_inset_aware: bool
    timestamp_fields_vertical: bool
    header_height: float
    back_width: float
    kebab_width: float


def media_layout(profile: UiProfile) -> MediaLayout:
    target = profile.touch_target
    return MediaLayout(
        vertical_page=True,
        frame_axis="vertical" if profile.category == "compact" else "horizontal",
        target_minimum=target,
        keyboard_inset_aware=True,
        # Vertical field stack on every profile: no horizontal overflow on
        # phones and the very same action hierarchy on PC.
        timestamp_fields_vertical=True,
        header_height=target,
        back_width=target,
        kebab_width=target,
    )


def video_direct_actions() -> tuple[str, ...]:
    """Same three direct video controls on every platform and width."""
    return VIDEO_DIRECT_ACTIONS


def media_context_actions(*, include_parent: bool = True) -> tuple[str, ...]:
    """Ordered app-bar kebab; the parent (global) entry is appended last."""
    return MEDIA_CONTEXT_ACTIONS + (
        (MEDIA_PARENT_ACTION,) if include_parent else ())


def panel_direct_actions() -> tuple[str, ...]:
    """Direct START/FINISH actions, applied without confirmation."""
    return PANEL_DIRECT_ACTIONS


def panel_context_actions() -> tuple[str, ...]:
    """Pure, width-independent ordering policy for every panel kebab."""
    return PANEL_CONTEXT_ACTIONS
