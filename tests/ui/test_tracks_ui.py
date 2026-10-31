"""M5 UI: tracks menu, shortcuts, sync dialog, subtitle loading, Settings card and preferences."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import Preferences, PreferencesStore, language_matches
from babarify_frame.core.errors import ErrorCode
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.core.models import SubtitlePosition, SubtitleStyle, TrackInfo, TrackKind
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.subtitles import format_delay, track_label

pytestmark = pytest.mark.ui


def mock_factory() -> EngineFactory:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    return factory


def make_window(qtbot: QtBot, store: PreferencesStore) -> MainWindow:
    win = MainWindow(mock_factory(), load_icon(), engine_name="mock", store=store)
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    return win


@pytest.fixture
def store(tmp_path: Path) -> PreferencesStore:
    return PreferencesStore(tmp_path / "settings.json")


@pytest.fixture
def window(qtbot: QtBot, store: PreferencesStore) -> Iterator[MainWindow]:
    win = make_window(qtbot, store)
    yield win
    win.close()


def playing(qtbot: QtBot, window: MainWindow, uri: str = "mock://clip?duration=60000") -> MockEngine:
    window.open_path(uri)
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    return engine


def selected(window: MainWindow, kind: TrackKind) -> list[int]:
    info = window.controller.media_info()
    assert info is not None
    return [t.id for t in info.tracks_of(kind) if t.selected]


def status_text(window: MainWindow) -> str:
    return window.statusBar().currentMessage()


def open_tracks_menu(window: MainWindow) -> QMenu:
    menu = window.player.controls.tracks_menu
    window.player.controls.tracks_menu_opening.emit(menu)
    return menu


def action_texts(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator() and a.text()]


# --------------------------------------------------------------- labels
@pytest.mark.parametrize(
    ("track", "expected"),
    [
        (
            TrackInfo(1, TrackKind.AUDIO, title="Director commentary", language="eng", codec="aac"),
            "Director commentary · English (aac)",
        ),
        (TrackInfo(1, TrackKind.AUDIO, title="Track 1 - [English]", language="eng"), "English"),
        (TrackInfo(1, TrackKind.SUBTITLE, language="fra", codec="subrip"), "French (subrip)"),
        (TrackInfo(1, TrackKind.SUBTITLE, title="English", language="eng"), "English"),
        (TrackInfo(7, TrackKind.SUBTITLE), "Track 3"),
        (TrackInfo(1, TrackKind.SUBTITLE, language="xyz"), "xyz"),
    ],
)
def test_track_label(track: TrackInfo, expected: str) -> None:
    assert track_label(track, 3) == expected


def test_delay_format_states_direction() -> None:
    assert (format_delay(0), format_delay(250), format_delay(-1500)) == ("0 ms", "+250 ms", "-1500 ms")


@pytest.mark.parametrize(
    ("preferred", "language", "match"),
    [
        ("fre", "fra", True),
        ("fre", "fre", True),
        ("ger", "deu", True),
        ("eng", "EN", True),
        ("eng", "fra", False),
        ("", "eng", False),
        ("eng", None, False),
    ],
)
def test_language_matching_accepts_both_iso_codes(preferred: str, language: str | None, match: bool) -> None:
    assert language_matches(preferred, language) is match


# --------------------------------------------------------- tracks menu
def test_tracks_menu_lists_and_switches_tracks(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    menu = open_tracks_menu(window)
    texts = action_texts(menu)
    for expected in (
        "English (aac)",
        "French (ac3)",
        "Off",
        "English (subrip)",
        "French (ass)",
        "Load subtitle file…",
        "Sync and delay…",
    ):
        assert expected in texts
    by_text = {a.text(): a for a in menu.actions()}
    assert by_text["English (aac)"].isChecked() and by_text["Off"].isChecked()
    by_text["French (ac3)"].trigger()
    assert selected(window, TrackKind.AUDIO) == [3]
    open_tracks_menu(window)
    {a.text(): a for a in menu.actions()}["French (ass)"].trigger()
    assert selected(window, TrackKind.SUBTITLE) == [5]
    open_tracks_menu(window)
    {a.text(): a for a in menu.actions()}["Off"].trigger()
    assert selected(window, TrackKind.SUBTITLE) == []


def test_tracks_button_disabled_without_media(window: MainWindow) -> None:
    assert not window.player.controls.tracks_button.isEnabled()
    assert not window.load_subtitle_action.isEnabled()


def test_shortcuts_cycle_tracks(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    window.show_page(window.player)
    window.next_subtitle_action.trigger()
    assert selected(window, TrackKind.SUBTITLE) == [4]
    assert status_text(window) == "Subtitles: English (subrip)"
    window.next_subtitle_action.trigger()
    window.next_subtitle_action.trigger()
    assert selected(window, TrackKind.SUBTITLE) == []
    assert status_text(window) == "Subtitles: Off"
    window.next_audio_action.trigger()
    assert selected(window, TrackKind.AUDIO) == [3]
    window.next_audio_action.trigger()
    assert selected(window, TrackKind.AUDIO) == [2]


def test_track_shortcuts_only_on_now_playing(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    window.show_page(window.settings)
    assert not window.next_subtitle_action.isEnabled()
    assert not window.subtitle_later_action.isEnabled()
    window.show_page(window.player)
    assert window.next_subtitle_action.isEnabled()


# ---------------------------------------------------------------- delays
def test_delay_shortcuts_step_and_report_units(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    window.show_page(window.player)
    window.subtitle_later_action.trigger()
    window.subtitle_later_action.trigger()
    assert window.controller.status().subtitle_delay_ms == 100
    assert status_text(window) == "Subtitle delay: +100 ms"
    window.audio_earlier_action.trigger()
    assert window.controller.status().audio_delay_ms == -50
    assert status_text(window) == "Audio delay: -50 ms"


def test_sync_dialog_applies_resets_and_follows_shortcuts(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    dialog = window.player.show_sync_dialog()
    dialog.subtitle.spin.setValue(-1200)
    assert window.controller.status().subtitle_delay_ms == -1200
    dialog.audio.plus.click()
    assert window.controller.status().audio_delay_ms == 50
    window.show_page(window.player)
    window.subtitle_later_action.trigger()
    assert dialog.subtitle.spin.value() == -1150
    dialog.subtitle.reset.click()
    dialog.audio.reset.click()
    status = window.controller.status()
    assert (status.subtitle_delay_ms, status.audio_delay_ms) == (0, 0)
    assert "later" in dialog.subtitle.spin.toolTip()
    dialog.close()


def test_delay_is_clamped_to_engine_limit(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    window.player.set_subtitle_delay(10_000_000)
    assert window.controller.status().subtitle_delay_ms == 60_000


def test_delays_reset_when_another_file_opens(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    dialog = window.player.show_sync_dialog()
    dialog.subtitle.spin.setValue(800)
    playing(qtbot, window, "mock://other")
    assert window.controller.status().subtitle_delay_ms == 0
    assert dialog.subtitle.spin.value() == 0
    dialog.close()


# ------------------------------------------------------- external files
def test_load_subtitle_file(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    sub = tmp_path / "movie.en.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    engine = playing(qtbot, window)
    window.player.load_subtitle_file(str(sub))
    assert f"add_subtitle:{sub.resolve()}" in engine.calls
    info = window.controller.media_info()
    assert info is not None
    assert [t.title for t in info.tracks_of(TrackKind.SUBTITLE) if t.selected] == ["movie.en.srt"]


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [("subs.xyz", b"1", "not supported"), ("gone.srt", None, "could not be found: gone.srt")],
)
def test_bad_subtitle_file_is_reported_and_playback_continues(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, name: str, content: bytes | None, message: str
) -> None:
    path = tmp_path / name
    if content is not None:
        path.write_bytes(content)
    playing(qtbot, window)
    window.player.load_subtitle_file(str(path))
    assert message in status_text(window).lower()
    assert window.player.state is S.PLAYING


def test_unreadable_subtitle_notice_reaches_status_bar(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    path = tmp_path / "broken.srt"
    path.write_bytes(b"\x00garbage")
    playing(qtbot, window)
    window.player.load_subtitle_file(str(path))
    qtbot.waitUntil(lambda: "Could not read subtitle file broken.srt" in status_text(window), timeout=2000)
    assert window.player.state is S.PLAYING
    assert window.player.message[0] != "Could not open this file"


def test_dropping_a_subtitle_adds_it_to_the_playing_video(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent

    sub = tmp_path / "dropped.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    engine = playing(qtbot, window)
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(sub))])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert any(c.startswith("add_subtitle:") for c in engine.calls)
    assert window.controller.status().uri == "mock://clip?duration=60000"  # not reopened


# ------------------------------------------------------- preferences
def test_preferred_languages_and_auto_subtitles(qtbot: QtBot, store: PreferencesStore) -> None:
    store.save(
        Preferences(subtitles_auto=True, preferred_audio_language="fre", preferred_subtitle_language="fre")
    )
    win = make_window(qtbot, store)
    playing(qtbot, win)
    assert selected(win, TrackKind.AUDIO) == [3]
    assert selected(win, TrackKind.SUBTITLE) == [5]
    win.close()


def test_subtitles_stay_off_by_default(qtbot: QtBot, window: MainWindow) -> None:
    playing(qtbot, window)
    assert selected(window, TrackKind.SUBTITLE) == []
    assert selected(window, TrackKind.AUDIO) == [2]


def test_auto_subtitles_fall_back_to_first_track(qtbot: QtBot, store: PreferencesStore) -> None:
    store.save(Preferences(subtitles_auto=True, preferred_subtitle_language="jpn"))
    win = make_window(qtbot, store)
    playing(qtbot, win)
    assert selected(win, TrackKind.SUBTITLE) == [4]
    win.close()


def test_subtitle_preferences_persist(store: PreferencesStore) -> None:
    style = SubtitleStyle("Arial", 140, "#FFFF00", 75, SubtitlePosition.RAISED)
    prefs = Preferences(
        subtitles_auto=True,
        preferred_audio_language="jpn",
        preferred_subtitle_language="eng",
        subtitle_style=style,
    )
    assert store.save(prefs)
    loaded = store.load()
    assert loaded.subtitle_style == style
    assert (loaded.subtitles_auto, loaded.preferred_audio_language, loaded.preferred_subtitle_language) == (
        True,
        "jpn",
        "eng",
    )


def test_untrusted_language_and_style_values_fall_back(store: PreferencesStore) -> None:
    store.path.write_text(
        '{"preferred_audio_language": "../../etc", "preferred_subtitle_language": 5, '
        '"subtitle_style": {"size_pct": 9999, "text_color": "javascript:", "position": 3}}',
        encoding="utf-8",
    )
    prefs = store.load()
    assert (prefs.preferred_audio_language, prefs.preferred_subtitle_language) == ("", "")
    assert prefs.subtitle_style.size_pct == 200
    assert prefs.subtitle_style.text_color == "#FFFFFF"
    assert prefs.subtitle_style.position is SubtitlePosition.BOTTOM


def test_settings_card_round_trips_and_applies_live_style(qtbot: QtBot, window: MainWindow) -> None:
    engine = playing(qtbot, window)
    page = window.settings
    page.subtitle_size.setValue(150)
    page.subtitle_color.setCurrentIndex(page.subtitle_color.findData("#FFFF00"))
    page.subtitle_position.setCurrentIndex(page.subtitle_position.findData("high"))
    page.subtitle_background.setCurrentIndex(page.subtitle_background.findData(75))
    style = window.player._prefs.subtitle_style
    assert (style.size_pct, style.text_color, style.position, style.background_opacity) == (
        150,
        "#FFFF00",
        SubtitlePosition.HIGH,
        75,
    )
    # The mock styles live; no restart, playback continues.
    assert engine.subtitle_style == style
    assert window.controller.engine is engine
    assert window.player.state is S.PLAYING


def test_missing_saved_font_is_flagged(qtbot: QtBot, store: PreferencesStore) -> None:
    store.save(Preferences(subtitle_style=SubtitleStyle(font_family="No Such Font 123")))
    win = make_window(qtbot, store)
    page = win.settings
    assert page.subtitle_font.currentText() == "No Such Font 123 (not installed)"
    assert not page.font_warning.isHidden()
    page.subtitle_font.setCurrentIndex(0)
    assert page.font_warning.isHidden()
    assert win.player._prefs.subtitle_style.font_family == ""
    win.close()


def test_restart_style_engine_keeps_position_tracks_and_delays(qtbot: QtBot, window: MainWindow) -> None:
    """Engines that apply style only at creation (libVLC) are restarted, keeping the user's choices."""
    engine = playing(qtbot, window)
    engine.advance(5000)
    window.player.select_audio(3)
    window.player.select_subtitle(5)
    window.player.set_subtitle_delay(400)
    original = engine.get_capabilities
    engine.get_capabilities = lambda: replace(original(), subtitle_style="restart")  # type: ignore[method-assign]
    page = window.settings
    page.subtitle_size.setValue(160)
    qtbot.waitUntil(
        lambda: window.player.engine_is_ready and window.controller.engine is not engine, timeout=5000
    )
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    new = window.controller.engine
    assert isinstance(new, MockEngine)
    assert new.options.subtitle_style.size_pct == 160
    assert window.controller.status().position_ms == 5000
    assert selected(window, TrackKind.AUDIO) == [3]
    assert selected(window, TrackKind.SUBTITLE) == [5]
    assert window.controller.status().subtitle_delay_ms == 400


def test_errors_for_subtitles_have_user_messages() -> None:
    from babarify_frame.core.errors import USER_MESSAGES

    assert ErrorCode.UNSUPPORTED in USER_MESSAGES and ErrorCode.MEDIA_NOT_FOUND in USER_MESSAGES
