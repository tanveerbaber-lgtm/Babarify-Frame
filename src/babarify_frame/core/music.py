"""Rules for playing music, free of any UI: repeat, shuffle and the animations' movement."""

from __future__ import annotations

import math
import random
from enum import StrEnum

AUTO_SWITCH_MS = 20_000
REST_LEVEL = 0.08
SLEEP_MINUTES = (15, 30, 45, 60, 90, 120)
_PEAK_FALL = 0.012
_ENVELOPE_FLOOR = 0.45


class RepeatMode(StrEnum):
    OFF = "off"
    ONE = "one"
    ALL = "all"

    def next(self) -> RepeatMode:
        order = list(RepeatMode)
        return order[(order.index(self) + 1) % len(order)]


class VisualStyle(StrEnum):
    """How audio with no picture is animated. AUTO moves through the others while it plays."""

    AUTO = "auto"
    MIRROR = "mirror"
    CAPSULES = "capsules"
    WAVES = "waves"
    CIRCLE = "circle"
    LIGHTS = "lights"


STYLE_LABELS = {
    VisualStyle.AUTO: "Change automatically",
    VisualStyle.MIRROR: "Mirror bars",
    VisualStyle.CAPSULES: "Capsules",
    VisualStyle.WAVES: "Waves",
    VisualStyle.CIRCLE: "Circle",
    VisualStyle.LIGHTS: "Lights",
}
STYLE_CYCLE = tuple(style for style in VisualStyle if style is not VisualStyle.AUTO)


def index_after_end(index: int, length: int, mode: RepeatMode) -> int | None:
    """Which queue item plays when the current one ends; None means playback stops."""
    if length <= 0:
        return None
    if mode is RepeatMode.ONE:
        return index
    if index + 1 < length:
        return index + 1
    return 0 if mode is RepeatMode.ALL else None


def shuffled(items: list[str], index: int, rng: random.Random | None = None) -> list[str]:
    """The same items in a random order, starting with the current one so it carries on playing."""
    if not 0 <= index < len(items):
        return list(items)
    others = items[:index] + items[index + 1 :]
    (rng or random).shuffle(others)
    return [items[index], *others]


def level(bar: int, time_ms: int) -> float:
    """How high an animated bar stands, from REST_LEVEL to 1. Decoration, not a measurement of the sound."""
    t = time_ms / 1000
    wave = (
        0.55 * abs(math.sin(t * 2.3 + bar * 0.9))
        + 0.3 * abs(math.sin(t * 4.1 + bar * 1.7))
        + 0.15 * abs(math.sin(t * math.pi * 2.7 + bar * 2.9))
    )
    return max(REST_LEVEL, min(1.0, REST_LEVEL + (1 - REST_LEVEL) * wave))


def envelope(bar: int, count: int) -> float:
    """Taller in the middle and lower at the ends, so a row of bars makes a shape."""
    if count <= 1:
        return 1.0
    return _ENVELOPE_FLOOR + (1 - _ENVELOPE_FLOOR) * math.sin(bar / (count - 1) * math.pi)


def peak(previous: float, current: float) -> float:
    """A peak jumps up with its bar and then falls slowly back to it."""
    return max(current, previous - _PEAK_FALL)


def auto_style(elapsed_ms: int) -> VisualStyle:
    return STYLE_CYCLE[(max(0, elapsed_ms) // AUTO_SWITCH_MS) % len(STYLE_CYCLE)]
