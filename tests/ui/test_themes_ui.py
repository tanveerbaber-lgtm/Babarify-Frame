"""Changing the colour theme while the app runs, and the equalizer's dials."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDial
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.themes import DEFAULT_THEME, THEMES
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui import controls, theme
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


def make_window(qtbot: QtBot, tmp_path: Path) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1.0")))
    win = MainWindow(
        factory, load_icon(), engine_name="mock", store=PreferencesStore(tmp_path / "settings.json")
    )
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    return win


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    win = make_window(qtbot, tmp_path)
    yield win
    win.close()
    theme.apply_theme(DEFAULT_THEME)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setStyleSheet(theme.STYLESHEET)


def choose(window: MainWindow, key: str) -> None:
    combo = window.settings.colour_theme
    combo.setCurrentIndex(combo.findData(key))


def test_settings_offer_every_theme(window: MainWindow) -> None:
    combo = window.settings.colour_theme
    assert [combo.itemData(i) for i in range(combo.count())] == list(THEMES)
    assert combo.currentData() == DEFAULT_THEME
    assert not combo.itemIcon(1).isNull(), "each shows its colours"


def test_choosing_a_theme_applies_at_once_and_is_remembered(window: MainWindow, tmp_path: Path) -> None:
    choose(window, "forest")
    assert theme.current_theme == "forest"
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    assert THEMES["forest"].bg in app.styleSheet()
    pixel = window.settings.grab().toImage().pixelColor(2, 2)
    assert pixel.name().upper() == THEMES["forest"].bg
    assert PreferencesStore(tmp_path / "settings.json").load().colour_theme == "forest"


def test_a_saved_theme_applies_when_the_app_starts(qtbot: QtBot, tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "settings.json")
    store.save(store.load().__class__(colour_theme="violet"))
    win = make_window(qtbot, tmp_path)
    try:
        assert theme.current_theme == "violet"
        assert win.settings.colour_theme.currentData() == "violet"
    finally:
        win.close()
        theme.apply_theme(DEFAULT_THEME)
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        app.setStyleSheet(theme.STYLESHEET)


def test_lit_buttons_take_the_new_colour(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Checks the colour asked for, not the picture: a machine without the icon font draws plain icons.
    asked: list[str] = []
    real_icon = controls.icon

    def recording_icon(widget, name, color=theme.TEXT):  # type: ignore[no-untyped-def]
        asked.append(color)
        return real_icon(widget, name, color)

    monkeypatch.setattr(controls, "icon", recording_icon)
    window.player.cycle_repeat()
    assert THEMES[DEFAULT_THEME].accent2 in asked
    asked.clear()
    choose(window, "sunset")
    assert THEMES["sunset"].accent2 in asked


def dialog_of(window: MainWindow):  # type: ignore[no-untyped-def]
    window.show_page(window.player)
    window.show_enhancements()
    dialog = window._enhancements
    assert dialog is not None
    return dialog


def test_the_dials_can_be_named_and_used_from_the_keyboard(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    for dial, name in ((dialog.bass, "Bass boost"), (dialog.preamp, "Preamp")):
        assert isinstance(dial, QDial)
        assert dial.accessibleName().startswith(name)
        assert dial.focusPolicy() & Qt.FocusPolicy.TabFocus
    dialog.close()


def test_the_bass_dial_turns_up_the_low_bands(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(True)
    dialog.bass.setValue(100)
    settings = dialog.equalizer()
    assert settings.bass_pct == 100
    assert settings.bands_db[0] == 12
    assert settings.bands_db[4:] == (0.0,) * 6
    assert dialog.eq_sliders[0].value() == 12, "the sliders show it"
    assert window.player.controller.engine is not None
    dialog.bass.setValue(0)
    assert dialog.equalizer().bands_db == (0.0,) * 10
    dialog.close()


def test_the_preamp_dial_sets_the_preamp(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(True)
    dialog.preamp.setValue(-6)
    assert dialog.equalizer().preamp_db == -6
    dialog.close()


def test_dials_are_off_with_the_equalizer(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(False)
    assert not dialog.bass.isEnabled() and not dialog.preamp.isEnabled()
    dialog.eq_enabled.setChecked(True)
    assert dialog.bass.isEnabled() and dialog.preamp.isEnabled()
    dialog.close()


def test_reset_clears_the_bass_dial(qtbot: QtBot, window: MainWindow) -> None:
    dialog = dialog_of(window)
    dialog.eq_enabled.setChecked(True)
    dialog.bass.setValue(60)
    dialog.reset_eq_button.click()
    assert dialog.bass.value() == 0
    assert dialog.equalizer().bands_db == (0.0,) * 10
    dialog.close()
