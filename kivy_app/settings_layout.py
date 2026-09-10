"""Pure settings policy, kept importable without Kivy."""

from __future__ import annotations

from dataclasses import dataclass

from .home_layout import abbrevia_id


@dataclass(frozen=True)
class FolderRow:
    folder_id: str
    label: str
    selected: bool
    removable: bool


def folder_rows(labels, current_id: str) -> tuple[FolderRow, ...]:
    values = tuple(labels)
    return tuple(FolderRow(
        folder_id, f"{name}  ·  {abbrevia_id(folder_id)}",
        folder_id == current_id, len(values) > 1,
    ) for folder_id, name in values)


def settings_return_action(view_kind: str, style_changed: bool) -> str:
    """How Settings should restore a retained view without losing its state."""
    if not style_changed:
        return "retain"
    if view_kind in ("home", "readonly"):
        return "rebuild-preserving-scroll"
    return "restyle-retained"
