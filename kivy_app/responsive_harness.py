"""Deterministic, headless responsive geometry harness."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Callable, Iterable

from .material import ScaleChoice, UiProfile, ViewportMetrics, adaptive_profile


@dataclass(frozen=True)
class WidgetBox:
    name: str
    x: float
    y: float
    width: float
    height: float
    interactive: bool = False
    text_clipped: bool = False


@dataclass(frozen=True)
class HarnessScenario:
    name: str
    metrics: ViewportMetrics
    scale: ScaleChoice = "auto"


@dataclass(frozen=True)
class GeometryIssue:
    kind: str
    message: str


DEFAULT_SCENARIOS = (
    HarnessScenario("phone-compact", ViewportMetrics(400, 800, input_mode="touch")),
    HarnessScenario("tablet-portrait", ViewportMetrics(720, 1024, input_mode="touch")),
    HarnessScenario("tablet-landscape", ViewportMetrics(1024, 720, input_mode="touch")),
    HarnessScenario("desktop-windows", ViewportMetrics(1280, 800, input_mode="pointer")),
    HarnessScenario("phone-compact-130", ViewportMetrics(400, 800, input_mode="touch"), "130"),
    HarnessScenario("tablet-landscape-130", ViewportMetrics(1024, 720, input_mode="touch"), "130"),
    HarnessScenario("desktop-windows-130", ViewportMetrics(1280, 800, input_mode="pointer"), "130"),
)


def validate_geometry(profile: UiProfile, boxes: Iterable[WidgetBox]) -> list[GeometryIssue]:
    items = list(boxes)
    issues: list[GeometryIssue] = []
    width, height = profile.viewport.width_dp, profile.viewport.height_dp
    for box in items:
        if box.width <= 0 or box.height <= 0:
            issues.append(GeometryIssue("zero-size", f"{box.name} ha dimensioni nulle."))
        if box.x < 0 or box.y < 0 or box.x + box.width > width or box.y + box.height > height:
            issues.append(GeometryIssue("out-of-bounds", f"{box.name} esce dal viewport."))
        if box.interactive and (box.width < profile.touch_target or box.height < profile.touch_target):
            issues.append(GeometryIssue("target-too-small", f"{box.name} è sotto il target minimo."))
        if box.text_clipped:
            issues.append(GeometryIssue("text-clipped", f"{box.name} contiene testo tagliato."))
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if _overlaps(left, right):
                issues.append(GeometryIssue("overlap", f"{left.name} si sovrappone a {right.name}."))
    return issues


def run_scenario(
    scenario: HarnessScenario,
    build_boxes: Callable[[UiProfile], Iterable[WidgetBox]],
) -> tuple[UiProfile, list[WidgetBox], list[GeometryIssue]]:
    profile = adaptive_profile(scenario.metrics, scenario.scale)
    boxes = list(build_boxes(profile))
    return profile, boxes, validate_geometry(profile, boxes)


def render_baseline(scenario: HarnessScenario, boxes: Iterable[WidgetBox]) -> bytes:
    """Render a stable SVG baseline suitable for byte-for-byte comparisons."""
    width, height = int(scenario.metrics.width_dp), int(scenario.metrics.height_dp)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    lines.append('<rect width="100%" height="100%" fill="#121416"/>')
    for box in sorted(boxes, key=lambda item: item.name):
        lines.append(
            f'<rect data-name="{escape(box.name)}" x="{box.x:g}" y="{box.y:g}" '
            f'width="{box.width:g}" height="{box.height:g}" fill="#252B2F" stroke="#55D6BE"/>'
        )
    lines.append("</svg>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_baseline(path: str | Path, content: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _overlaps(left: WidgetBox, right: WidgetBox) -> bool:
    return (
        left.x < right.x + right.width and left.x + left.width > right.x
        and left.y < right.y + right.height and left.y + left.height > right.y
    )
