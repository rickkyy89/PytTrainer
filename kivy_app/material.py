"""Adaptive Material contract shared by the Kivy screens.

This module deliberately has no Kivy import.  Platform adapters translate its
logical values to widgets, while tests can exercise the complete layout policy
without a Window or a display.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Category = Literal["compact", "medium", "expanded"]
InputMode = Literal["touch", "pointer"]
ScaleChoice = Literal["auto", "100", "115", "130"]
TextChoice = Literal["auto"] | int
VALID_SCALE_CHOICES = frozenset(("auto", "100", "115", "130"))
TEXT_SIZE_MIN = 14
TEXT_SIZE_MAX = 32
TEXT_SIZE_STEP = 1


@dataclass(frozen=True)
class ViewportMetrics:
    width_dp: float
    height_dp: float
    system_density: float = 1.0
    input_mode: InputMode = "pointer"

    def __post_init__(self) -> None:
        if self.width_dp < 0 or self.height_dp < 0 or self.system_density <= 0:
            raise ValueError("Le metriche viewport devono essere positive.")
        if self.input_mode not in ("touch", "pointer"):
            raise ValueError("input_mode deve essere touch o pointer.")


@dataclass(frozen=True)
class UiTokens:
    colors: dict[str, str]
    typography: dict[str, float]
    spacing: dict[str, float]
    dimensions: dict[str, float]
    icons: dict[str, object]


@dataclass(frozen=True)
class LayoutPlan:
    columns: int
    field_labels_above: bool
    frames_axis: Literal["vertical", "horizontal"]
    master_detail: bool


@dataclass(frozen=True)
class UiProfile:
    category: Category
    scale: float
    touch_target: float
    tokens: UiTokens
    orientation: Literal["portrait", "landscape"]
    viewport: ViewportMetrics

    def layout(self, screen: str) -> LayoutPlan:
        """Return a deterministic layout policy for a named screen."""
        del screen  # current policy is shared; screen-specific additions stay internal.
        if self.category == "compact":
            return LayoutPlan(1, True, "vertical", False)
        if self.category == "medium":
            return LayoutPlan(2, False, "horizontal", False)
        return LayoutPlan(2, False, "horizontal", True)


def adaptive_profile(metrics: ViewportMetrics, scale: ScaleChoice = "auto",
                     text: TextChoice | None = None) -> UiProfile:
    """Resolve category, scale, targets and tokens from injected metrics."""
    if scale not in VALID_SCALE_CHOICES:
        raise ValueError(f"Scala non valida: {scale!r}.")
    text = testo_corrente() if text is None else valida_testo(text)
    width = metrics.width_dp
    category: Category = "compact" if width < 600 else "medium" if width < 960 else "expanded"
    multiplier = {"auto": 1.0, "100": 1.0, "115": 1.15, "130": 1.30}[scale]
    target = 48.0 if metrics.input_mode == "touch" else 40.0
    base = _tokens(target, _body_text_size(metrics, category, text))
    tokens = UiTokens(
        colors=base.colors,
        # Text is deliberately independent from UI scale: users can enlarge
        # controls/spacing without enlarging type a second time.
        typography=base.typography,
        spacing={name: value * multiplier for name, value in base.spacing.items()},
        dimensions={name: value * multiplier for name, value in base.dimensions.items()},
        icons={**base.icons, "size_sm": base.icons["size_sm"] * multiplier,
               "size_md": base.icons["size_md"] * multiplier,
               "size_lg": base.icons["size_lg"] * multiplier},
    )
    return UiProfile(
        category=category,
        scale=metrics.system_density * multiplier,
        touch_target=target,
        tokens=tokens,
        orientation="landscape" if metrics.width_dp > metrics.height_dp else "portrait",
        viewport=metrics,
    )


def input_mode_for_platform(platform: str | None = None) -> InputMode:
    """Single decision point: touch targets only on Android-like platforms."""
    import sys
    return "touch" if (platform or sys.platform) == "android" else "pointer"


_scala_corrente: ScaleChoice = "auto"
_testo_corrente: TextChoice = "auto"


def scala_corrente() -> ScaleChoice:
    return _scala_corrente


def imposta_scala(valore: ScaleChoice) -> ScaleChoice:
    """Set the process-wide user scale (device-local, never in bundles)."""
    global _scala_corrente
    if valore not in VALID_SCALE_CHOICES:
        raise ValueError(f"Scala non valida: {valore!r}.")
    _scala_corrente = valore
    return valore


def valida_testo(valore: object) -> TextChoice:
    """Normalize a persisted text preference and reject out-of-range values."""
    if valore == "auto":
        return "auto"
    if isinstance(valore, bool):
        raise ValueError("Dimensione testo non valida.")
    try:
        numero = int(valore)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dimensione testo non valida.") from exc
    if not TEXT_SIZE_MIN <= numero <= TEXT_SIZE_MAX:
        raise ValueError(f"Il testo deve essere tra {TEXT_SIZE_MIN} e {TEXT_SIZE_MAX} pt.")
    return numero


def testo_corrente() -> TextChoice:
    return _testo_corrente


def imposta_testo(valore: TextChoice) -> TextChoice:
    """Set process-wide type size (device-local and separate from UI scale)."""
    global _testo_corrente
    _testo_corrente = valida_testo(valore)
    return _testo_corrente


def etichetta_testo(valore: TextChoice | None = None) -> str:
    valore = testo_corrente() if valore is None else valida_testo(valore)
    return "Testo auto" if valore == "auto" else f"Testo {valore} pt"


def hex_to_rgba(valore: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """Material token colors are stored as #RRGGBB; widgets need 0-1 rgba."""
    v = valore.lstrip("#")
    return (int(v[0:2], 16) / 255.0, int(v[2:4], 16) / 255.0,
            int(v[4:6], 16) / 255.0, alpha)


def markup_px(profile: UiProfile, size_sp: float, *, correction: float = 1.0) -> int:
    """Convert an sp/dp typography token to Kivy markup's physical pixels."""
    return max(1, int(round(size_sp * correction * profile.viewport.system_density)))


def _px_per_dp(window) -> float:
    """Pixel-per-dp factor as Kivy widget geometry actually uses it.

    ``Window.density`` is unreliable (Kivy keeps it at 1.0 on Android while
    ``Window.width`` is in device pixels), so ``metrics.dp(1)`` is the only
    value consistent with how widgets are sized. Falls back to the window
    attribute in headless tests that pass no real metrics.
    """
    try:
        from kivy.metrics import dp
    except ImportError:
        return getattr(window, "density", None) or 1.0
    return dp(1) or 1.0


def profile_for_window(window, *, input_mode: InputMode | None = None,
                       scale: ScaleChoice | None = None,
                       text: TextChoice | None = None,
                       px_per_dp: float | None = None) -> UiProfile:
    """Kivy adapter kept at the seam; screens do not read density themselves."""
    if input_mode is None:
        input_mode = input_mode_for_platform()
    if scale is None:
        scale = scala_corrente()
    if px_per_dp is None:
        px_per_dp = _px_per_dp(window)
    return adaptive_profile(
        ViewportMetrics(window.width / px_per_dp, window.height / px_per_dp,
                        px_per_dp, input_mode),
        scale, text,
    )


def _body_text_size(metrics: ViewportMetrics, category: Category,
                    choice: TextChoice) -> float:
    if choice != "auto":
        return float(choice)
    # A phone is read farther away and primarily by touch.  Keep Android/touch
    # at 21sp (never below the requested 20sp); wider pointer layouts can use a
    # slightly denser but still substantially larger default than the old 16sp.
    if metrics.input_mode == "touch":
        return 21.0 if category == "compact" else 20.0
    return 18.0 if category == "expanded" else 19.0


def _tokens(target: float, body: float) -> UiTokens:
    ratio = body / 16.0
    return UiTokens(
        colors={
            "background": "#121416", "surface": "#1B1F22", "surface_variant": "#252B2F",
            "surface_container": "#20272A", "text": "#F2F5F4", "muted": "#AAB5B3",
            "primary": "#55D6BE", "on_primary": "#00382F",
            "primary_container": "#164E46", "on_primary_container": "#B8F3E8",
            "coral": "#FF8A7A", "on_coral": "#45100A",
            "secondary": "#FF8A7A", "on_secondary": "#45100A",
            "secondary_container": "#65302A", "on_secondary_container": "#FFDAD5",
            "error": "#FF7D8A", "error_container": "#5C1F29", "on_error": "#410009",
            "accent": "#55D6BE", "focus": "#55D6BE", "disabled": "#66716F",
        },
        typography={"title": round(24.0 * ratio, 2), "section": round(18.0 * ratio, 2),
                    "body": body, "label": max(14.0, round(body - 2.0, 2)),
                    "caption": max(12.0, round(body - 4.0, 2))},
        spacing={"xxs": 2.0, "xs": 4.0, "sm": 8.0, "md": 12.0, "lg": 20.0, "xl": 28.0},
        dimensions={
            "toolbar_height": max(48.0, target), "field_height": max(48.0, target),
            "card_radius": 10.0, "border_width": 1.0, "content_max_width": 1120.0,
            "dialog_max_width": 560.0, "frame_min_height": 180.0,
        },
        icons={"family": "bundled-material", "size_sm": 18.0, "size_md": 24.0, "size_lg": 32.0},
    )


class ScalePreferenceStore:
    """Atomic device-local store for scale and global text preferences."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def load_scale(self) -> ScaleChoice:
        try:
            choice = json.loads(self.path.read_text(encoding="utf-8"))["scale"]
        except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError, TypeError):
            return "auto"
        return choice if choice in VALID_SCALE_CHOICES else "auto"

    def load_text(self) -> TextChoice:
        try:
            choice = json.loads(self.path.read_text(encoding="utf-8")).get("text", "auto")
            return valida_testo(choice)
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            return "auto"

    def _load_mapping(self) -> dict[str, object]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _save(self, **updates: object) -> None:
        values = self._load_mapping()
        values.update(updates)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(values), encoding="utf-8")
        os.replace(temporary, self.path)

    def save_scale(self, choice: ScaleChoice) -> None:
        if choice not in VALID_SCALE_CHOICES:
            raise ValueError(f"Scala non valida: {choice!r}.")
        self._save(scale=choice)

    def save_text(self, choice: TextChoice) -> None:
        self._save(text=valida_testo(choice))


def primitive_specs(profile: UiProfile) -> dict[str, dict[str, object]]:
    """Return shared style specs consumed by Kivy widget adapters."""
    d = profile.tokens.dimensions
    return {
        "text": {"color": profile.tokens.colors["text"], "font_size": profile.tokens.typography["body"]},
        "button": {"min_height": profile.touch_target, "min_width": profile.touch_target},
        "field": {"height": d["field_height"], "font_size": profile.tokens.typography["body"]},
        "card": {"radius": d["card_radius"], "border_width": d["border_width"]},
        "toolbar": {"height": d["toolbar_height"]},
        "menu": {"min_height": profile.touch_target},
        "dialog": {"max_width": d["dialog_max_width"]},
    }
