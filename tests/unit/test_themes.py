"""Every colour theme must stay readable, and the bass dial must move only the low bands."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from babarify_frame.configuration.preferences import Preferences
from babarify_frame.core.enhancements import EqualizerSettings, with_bass
from babarify_frame.core.themes import DEFAULT_THEME, THEMES
from babarify_frame.ui import theme


def _luminance(colour: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.fixture(autouse=True)
def back_to_default() -> Iterator[None]:
    yield
    theme.apply_theme(DEFAULT_THEME)


@pytest.mark.parametrize("key", THEMES)
def test_every_theme_meets_the_contrast_rules(key: str) -> None:
    p = THEMES[key]
    for surface in (p.bg, p.surface, p.raised):
        assert contrast(p.text, surface) >= 4.5, f"text on {surface}"
        assert contrast(p.muted, surface) >= 4.5, f"muted text on {surface}"
        assert contrast(p.control_border, surface) >= 3, f"control border on {surface}"
    assert contrast(p.accent2, p.bg) >= 4.5, "highlight on the page"
    assert contrast(p.accent2, p.surface) >= 3, "focus ring on a panel"
    assert contrast(p.on_accent, p.accent) >= 4.5, "icon on the accent"
    assert contrast(p.on_accent, p.accent2) >= 4.5, "text on the accent's bright end"
    assert contrast(p.red, p.bg) >= 4.5, "an error on the page"
    assert contrast(p.amber, p.surface) >= 4.5, "a warning on a panel"
    assert contrast(p.green, p.surface) >= 3, "a ticked box on a panel"
    assert contrast(p.on_accent, p.amber) >= 3 or contrast(p.on_accent, p.red) >= 3, "badge text"


def test_applying_a_theme_changes_the_colours_and_stylesheet() -> None:
    before = theme.STYLESHEET
    theme.apply_theme("forest")
    assert THEMES["forest"].bg == theme.BG
    assert THEMES["forest"].accent2 == theme.CYAN
    assert THEMES["forest"].accent in theme.ACCENT_GRADIENT
    assert before != theme.STYLESHEET
    assert THEMES["forest"].bg in theme.STYLESHEET
    assert THEMES["ocean"].bg not in theme.STYLESHEET


def test_the_light_theme_changes_the_text_and_button_colours_too() -> None:
    theme.apply_theme("light")
    assert theme.is_light()
    assert (THEMES["light"].text, "#FFFFFF") == (theme.TEXT, theme.ON_ACCENT)
    assert THEMES["light"].text in theme.STYLESHEET
    assert THEMES["ocean"].text not in theme.STYLESHEET
    assert "#04101F" not in theme.STYLESHEET
    theme.apply_theme(DEFAULT_THEME)
    assert not theme.is_light()
    assert THEMES[DEFAULT_THEME].text == theme.TEXT


def test_the_default_theme_is_the_original_look() -> None:
    theme.apply_theme("rose")
    theme.apply_theme(DEFAULT_THEME)
    assert (theme.BG, theme.BLUE, theme.CYAN) == ("#070B15", "#3B82F6", "#22D3EE")


def test_an_unknown_theme_falls_back_to_the_default() -> None:
    theme.apply_theme("no such theme")
    assert theme.current_theme == DEFAULT_THEME
    assert Preferences.from_dict({"colour_theme": "no such theme"}).colour_theme == DEFAULT_THEME
    assert Preferences.from_dict({"colour_theme": "amber"}).colour_theme == "amber"


def test_bass_moves_only_the_lowest_bands() -> None:
    flat = (0.0,) * 10
    full = with_bass(flat, 0, 100)
    assert full[0] == 12
    assert full[0] > full[1] > full[2] > full[3] > 0
    assert full[4:] == (0.0,) * 6


def test_turning_bass_back_returns_every_band_exactly() -> None:
    start = (3.0, -2.0, 1.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    now = start
    previous = 0
    for setting in (17, 33, 58, 91, 44, 6, 0):
        now = with_bass(now, previous, setting)
        previous = setting
    assert now == start


def test_bass_stays_in_range() -> None:
    assert with_bass((19.0,) * 10, 0, 100)[0] == 20


def test_bass_setting_is_saved_and_checked() -> None:
    saved = EqualizerSettings(bass_pct=40).to_dict()
    assert EqualizerSettings.from_dict(saved).bass_pct == 40
    assert EqualizerSettings.from_dict({"bass_pct": 900}).bass_pct == 100
    assert EqualizerSettings.from_dict({"bass_pct": "loud"}).bass_pct == 0


def test_the_font_is_arial_with_bold_titles_and_headings() -> None:
    sheet = theme.STYLESHEET
    assert 'font-family: "Arial"' in sheet
    assert "Segoe" not in sheet and "monospace" not in sheet
    assert "font-weight: 600" not in sheet
    for role in ("display", "title", "subtitle"):
        rule = next(line for line in sheet.splitlines() if line.startswith(f"QLabel#{role} "))
        assert "font-weight: 700" in rule, role
    body = next(line for line in sheet.splitlines() if line.startswith("* {"))
    assert "font-weight" not in body, "body text stays regular"
