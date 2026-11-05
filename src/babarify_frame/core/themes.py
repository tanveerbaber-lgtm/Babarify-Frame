"""The colour themes. All are dark, so the light text colours stay readable on every one of them."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THEME = "ocean"


@dataclass(frozen=True)
class Palette:
    label: str
    bg: str
    surface: str
    raised: str
    pressed: str
    border: str
    control_border: str
    muted: str
    accent: str  # BLUE in the default theme: buttons and gradients
    accent2: str  # CYAN in the default theme: focus, selection and highlights


THEMES = {
    "ocean": Palette(
        "Ocean",
        "#070B15",
        "#0E1628",
        "#16213A",
        "#1E2B48",
        "#22304D",
        "#5E7096",
        "#8A9AB5",
        "#3B82F6",
        "#22D3EE",
    ),
    "sunset": Palette(
        "Sunset",
        "#160A12",
        "#241320",
        "#351C2E",
        "#46263D",
        "#4A2A40",
        "#8E6680",
        "#B495A9",
        "#F97316",
        "#FB7185",
    ),
    "forest": Palette(
        "Forest",
        "#06130F",
        "#0D211B",
        "#153228",
        "#1C4134",
        "#214A3B",
        "#568573",
        "#8DB0A2",
        "#10B981",
        "#5EEAD4",
    ),
    "violet": Palette(
        "Violet",
        "#0E0A1C",
        "#191233",
        "#251B49",
        "#30245C",
        "#3A2C69",
        "#7566A8",
        "#A89CCB",
        "#A78BFA",
        "#E879F9",
    ),
    "amber": Palette(
        "Amber",
        "#11100B",
        "#1E1B12",
        "#2C281A",
        "#3A3522",
        "#443D27",
        "#80744B",
        "#AFA582",
        "#F59E0B",
        "#FDE047",
    ),
    "rose": Palette(
        "Rose",
        "#170A10",
        "#27111B",
        "#3A1828",
        "#4A2033",
        "#55253C",
        "#94607A",
        "#BE95A9",
        "#FB7185",
        "#F9A8D4",
    ),
}
