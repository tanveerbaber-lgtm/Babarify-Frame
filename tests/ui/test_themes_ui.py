"""Changing the colour theme while the app runs, and the equalizer's dials."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QDial, QLabel, QToolButton
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.themes import DEFAULT_THEME, THEMES
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui import controls, theme
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.audio_view import colour_from
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

    def recording_icon(widget, name, color=None):  # type: ignore[no-untyped-def]
        asked.append(color or theme.TEXT)
        return real_icon(widget, name, color)

    monkeypatch.setattr(controls, "icon", recording_icon)
    window.player.cycle_repeat()
    assert THEMES[DEFAULT_THEME].accent2 in asked
    asked.clear()
    choose(window, "sunset")
    assert THEMES["sunset"].accent2 in asked


def test_light_redraws_every_button_and_the_rail_in_its_colours(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    real_icon = controls.icon

    def recording_icon(widget, name, color=None):  # type: ignore[no-untyped-def]
        asked.append(color or theme.TEXT)
        return real_icon(widget, name, color)

    monkeypatch.setattr(controls, "icon", recording_icon)
    choose(window, "light")
    assert THEMES["light"].text in asked, "ordinary buttons"
    assert "#FFFFFF" in asked, "the play button"
    assert THEMES[DEFAULT_THEME].text not in asked
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    assert app.styleHints().colorScheme() == Qt.ColorScheme.Light
    pixel = window.settings.grab().toImage().pixelColor(2, 2)
    assert pixel.name().upper() == THEMES["light"].bg
    choose(window, DEFAULT_THEME)


def test_the_rail_has_a_quick_theme_button_under_settings(window: MainWindow, tmp_path: Path) -> None:
    assert window.nav_theme.isVisible()
    assert window.nav_theme.accessibleName() == "Colour theme"
    assert window.nav_theme.y() > window.nav_settings.y()
    assert not window.nav_theme.isCheckable(), "it opens a list rather than a page"
    menu = window.build_theme_menu()
    actions = menu.actions()
    assert [action.text() for action in actions] == [palette.label for palette in THEMES.values()]
    assert [action.text() for action in actions if action.isChecked()] == ["Ocean"]
    next(action for action in actions if action.text() == "Forest").trigger()
    assert theme.current_theme == "forest"
    assert window.settings.colour_theme.currentData() == "forest", "Settings agrees"
    assert PreferencesStore(tmp_path / "settings.json").load().colour_theme == "forest"
    assert [a.text() for a in window.build_theme_menu().actions() if a.isChecked()] == ["Forest"]
    choose(window, DEFAULT_THEME)


def test_the_rail_has_a_quick_animation_button_under_theme(window: MainWindow, tmp_path: Path) -> None:
    assert window.nav_animation.isVisible()
    assert window.nav_animation.accessibleName() == "Animation for audio"
    assert window.nav_animation.y() > window.nav_theme.y()
    actions = window.build_animation_menu().actions()
    assert [a.text() for a in actions if a.isChecked()] == ["Change automatically"]
    next(a for a in actions if a.text() == "Circle").trigger()
    assert window.player.audio_view.visualizer.style_choice.value == "circle"
    assert window.settings.visual_style.currentData() == "circle", "Settings agrees"
    assert PreferencesStore(tmp_path / "settings.json").load().visual_style == "circle"
    assert [a.text() for a in window.build_animation_menu().actions() if a.isChecked()] == ["Circle"]


def test_settings_replaces_about_in_the_group_at_the_bottom_of_the_rail(window: MainWindow) -> None:
    rail_buttons = [b for b in window.findChildren(QToolButton) if b.objectName() == "navButton"]
    assert "About" not in [b.text() for b in rail_buttons]
    assert {b.width() for b in rail_buttons} == {window.nav_home.width()}, "lined up"
    for button in rail_buttons:
        assert button.sizeHint().width() <= button.width(), f"{button.text()} would be cut off"
    assert max(rail_buttons, key=lambda b: b.y()) is window.nav_animation
    gap = window.nav_settings.y() - window.nav_player.geometry().bottom()
    assert gap > window.nav_theme.y() - window.nav_settings.geometry().bottom(), (
        "set apart from the pages above"
    )
    window.nav_settings.click()
    assert window.current_page() is window.settings


def test_home_shows_the_name_once_in_the_brand_colours(window: MainWindow) -> None:
    labels = [label.text() for label in window.home.findChildren(QLabel)]
    assert labels.count("Babarify Media Player") == 1
    assert "BABARIFY" not in labels
    title = next(
        label for label in window.home.findChildren(QLabel) if label.text() == "Babarify Media Player"
    )
    window.show_page(window.home)
    image = title.grab().toImage()

    def closest(colour: str, columns: range) -> int:
        target = QColor(colour)
        return min(
            abs(image.pixelColor(x, y).red() - target.red())
            + abs(image.pixelColor(x, y).green() - target.green())
            + abs(image.pixelColor(x, y).blue() - target.blue())
            for x in columns
            for y in range(image.height())
        )

    third = image.width() // 3
    assert closest(theme.BLUE, range(0, third)) < 40, "blue at the start"
    assert closest(theme.CYAN, range(image.width() - third, image.width())) < 40, "cyan at the end"


def test_a_songs_colours_stay_readable_in_light(window: MainWindow) -> None:
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("#102040"))
    choose(window, "light")
    colour = colour_from(image)
    assert colour.valueF() > 0.9, "pale, for dark text"
    choose(window, DEFAULT_THEME)
    assert colour_from(image).valueF() <= 0.31


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


def test_the_status_bar_is_hidden_unless_chosen(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    bar = window.statusBar()
    assert bar.isHidden()
    window.player.status_changed.emit("A message")
    assert bar.isHidden(), "a message doesn't bring it back"
    window.settings.show_status_bar.setChecked(True)
    assert not bar.isHidden()
    assert window.status_bar_action.isChecked()
    assert PreferencesStore(tmp_path / "settings.json").load().show_status_bar
    window.status_bar_action.setChecked(False)
    assert bar.isHidden()
    assert not window.settings.show_status_bar.isChecked()
    assert not PreferencesStore(tmp_path / "settings.json").load().show_status_bar


def test_leaving_full_screen_keeps_the_status_bar_as_chosen(qtbot: QtBot, window: MainWindow) -> None:
    window.show_page(window.player)
    window.toggle_fullscreen()
    window.exit_fullscreen()
    assert window.statusBar().isHidden()
    window.status_bar_action.setChecked(True)
    window.toggle_fullscreen()
    assert window.statusBar().isHidden(), "full screen hides it either way"
    window.exit_fullscreen()
    assert not window.statusBar().isHidden()
