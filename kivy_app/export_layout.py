"""Pure responsive policy for the Google Doc export surface.

Like the other layout modules this one has no Kivy import: the screen
translates these numbers into widgets, while tests verify that the same
minimal hierarchy (one visible primary action, contextual kebab overflow)
fits every harness viewport without horizontal overflow.
"""

from __future__ import annotations

from dataclasses import dataclass

from .material import UiProfile


@dataclass(frozen=True)
class ExportLayout:
    header_height: float
    back_width: float
    kebab_width: float
    primary_height: float
    title_min_width: float
    minimum_target: float


EXPORT_PRIMARY_READY = "Avvia"
EXPORT_PRIMARY_GENERATED = "Apri documento"
# Ordered contextual kebab; "Riprendi" and "Condividi PDF" only make sense
# once a document exists, "Rigenera nuovo" (with its confirmation popup) is
# always available from the pre-generation state too.
EXPORT_CONTEXT_READY = ("Rigenera nuovo",)
EXPORT_CONTEXT_GENERATED = ("Condividi PDF", "Riprendi", "Rigenera nuovo")
EXPORT_PARENT_ACTION = "Impostazioni"


def export_layout(profile: UiProfile) -> ExportLayout:
    target = profile.touch_target
    return ExportLayout(
        header_height=target,
        back_width=target,
        kebab_width=target,
        primary_height=target,
        title_min_width=120.0,
        minimum_target=target,
    )


def export_primary_action(*, generated: bool) -> str:
    """Exactly one visible primary action, appropriate to the state."""
    return EXPORT_PRIMARY_GENERATED if generated else EXPORT_PRIMARY_READY


def export_overflow_actions(*, generated: bool,
                            include_parent: bool = True) -> tuple[str, ...]:
    """Ordered contextual kebab, identical on every platform and width.

    The parent (global) entry is appended last and only when the screen was
    given an ``on_menu`` callback, mirroring the editor app-bar contract.
    """
    context = EXPORT_CONTEXT_GENERATED if generated else EXPORT_CONTEXT_READY
    return context + ((EXPORT_PARENT_ACTION,) if include_parent else ())
