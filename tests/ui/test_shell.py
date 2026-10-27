"""App shell and player tests against the deterministic mock engine (plus real-app smoke tests)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QAbstractButton, QSlider, QWidget
from pytestqt.qtbot import QtBot

from babarify_frame import PRODUCT_NAME, TAGLINE
from babarify_frame.configuration.preferences import Preferences, PreferencesStore, WindowGeometry
from babarify_frame.core.errors import USER_MESSAGES, ErrorCode
from babarify_frame.core.models import EngineOptions
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui import pages
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.controls import COMPACT_WIDTH, NARROW_WIDTH, rate_label
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.widgets import format_time

pytestmark = pytest.mark.ui

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "generated"


def mock_factory() -> EngineFactory:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    return factory


def broken_factory() -> EngineFactory:
    def fail(_options: EngineOptions) -> PlaybackEngine:
        raise OSError("libvlc.dll not found")

    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", fail, lambda: EngineProbe("mock", False)))
    return factory


def make_window(
    qtbot: QtBot, store: PreferencesStore, factory: EngineFactory | None = None, start: bool = True
) -> MainWindow:
    win = MainWindow(factory or mock_factory(), load_icon(), engine_name="mock", store=store)
    qtbot.addWidget(win)
    win.show()
    if start:
        win.start_engine()
        if factory is None:
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


def engine_of(window: MainWindow) -> MockEngine:
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    return engine


def status(window: MainWindow):  # type: ignore[no-untyped-def]
    return window.controller.status()


# ------------------------------------------------------------------ shell
def test_branding_and_home_page(window: MainWindow) -> None:
    assert window.windowTitle() == PRODUCT_NAME
    assert not window.windowIcon().isNull()
    assert window.current_page() is window.home
    assert window.nav_home.isChecked()
    texts = {label.text() for label in window.home.findChildren(pages.home.QLabel)}
    assert {PRODUCT_NAME, TAGLINE} <= texts


def test_icon_resources_exist() -> None:
    assert {s.width() for s in load_icon().availableSizes()} >= {16, 32, 256}


def test_navigation_by_rail_and_shortcuts(window: MainWindow, qtbot: QtBot) -> None:
    qtbot.mouseClick(window.nav_settings, Qt.MouseButton.LeftButton)
    assert window.current_page() is window.settings
    assert window.nav_settings.isChecked() and not window.nav_home.isChecked()
    window.player_action.trigger()  # Ctrl+2
    assert window.current_page() is window.player
    window.home_action.trigger()  # Ctrl+1
    assert window.current_page() is window.home


def test_navigation_shortcut_keys(window: MainWindow) -> None:
    keys = {
        a.text(): a.shortcuts()[0].toString()
        for a in (window.home_action, window.player_action, window.settings_action)
    }
    assert keys == {"&Home": "Ctrl+1", "&Now Playing": "Ctrl+2", "&Settings": "Ctrl+3"}


def test_open_switches_to_player_page(window: MainWindow) -> None:
    window.open_path("mock://clip?duration=60000")
    assert window.current_page() is window.player
    assert "mock://clip" in window.windowTitle()


def test_playback_shortcuts_only_on_player_page(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    assert window.play_action.isEnabled()
    window.show_page(window.settings)
    assert not window.play_action.isEnabled()
    assert not window.mute_action.isEnabled()
    qtbot.keyClick(window, Qt.Key.Key_Space)
    assert status(window).state is S.PLAYING  # Space did nothing outside the player page
    window.show_page(window.player)
    qtbot.keyClick(window, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: status(window).state is S.PAUSED)


def test_engine_unavailable_is_explained(qtbot: QtBot, store: PreferencesStore) -> None:
    win = make_window(qtbot, store, factory=broken_factory())
    qtbot.waitUntil(lambda: win.player.message[0] == "Playback engine unavailable", timeout=5000)
    assert USER_MESSAGES[ErrorCode.ENGINE_UNAVAILABLE] in win.player.message[1]
    assert win.current_page() is win.player
    assert not win.open_action.isEnabled()
    assert not win.home.open_button.isEnabled()
    win.close()


def test_file_opened_before_engine_ready_is_opened_afterwards(qtbot: QtBot, store: PreferencesStore) -> None:
    win = make_window(qtbot, store, start=False)
    win.open_path("mock://early?duration=5000")  # e.g. a file passed on the command line
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    assert status(win).state is S.PLAYING
    assert status(win).uri == "mock://early?duration=5000"
    win.close()


# ----------------------------------------------------------------- player
def test_open_enables_controls(window: MainWindow) -> None:
    window.open_path("mock://clip?duration=60000")
    c = window.player.controls
    assert c.play_button.isEnabled() and c.stop_button.isEnabled() and c.seek.isEnabled()
    assert window.forward_action.isEnabled()
    assert c.title_label.toolTip() == "mock://clip?duration=60000"


def test_position_display_follows_engine(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    engine_of(window).advance(12_000)
    c = window.player.controls
    qtbot.waitUntil(lambda: c.time_label.text() == format_time(12_000), timeout=2000)
    assert c.seek.value() == 12_000
    assert c.duration_label.text() == format_time(60_000)


def test_seek_is_clamped_and_uses_preferred_step(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    window.player.seek_to(90_000)
    assert status(window).position_ms == 60_000
    qtbot.keyClick(window, Qt.Key.Key_Left)  # default step 10 s
    assert status(window).position_ms == 50_000
    window.settings.seek_step.setCurrentIndex(window.settings.seek_step.findData(30))
    qtbot.keyClick(window, Qt.Key.Key_Left)
    assert status(window).position_ms == 20_000
    window.player.seek_to(-5)
    assert status(window).position_ms == 0


def test_slider_click_requests_seek(window: MainWindow) -> None:
    window.open_path("mock://clip?duration=60000")
    window.player.controls.seek.seek_requested.emit(20_000)
    assert status(window).position_ms == 20_000


def test_volume_mute_and_keys(window: MainWindow, qtbot: QtBot) -> None:
    window.show_page(window.player)
    window.player.controls.volume.setValue(40)
    assert status(window).volume == 40
    qtbot.keyClick(window, Qt.Key.Key_Down)
    assert status(window).volume == 35
    qtbot.keyClick(window, Qt.Key.Key_M)
    assert status(window).muted is True
    assert window.player.controls.mute_button.accessibleName() == "Unmute"
    window.player.controls.volume.setValue(50)  # raising the volume unmutes
    assert status(window).muted is False


def test_speed_menu(window: MainWindow) -> None:
    window.open_path("mock://clip")
    window.player.controls.rate_selected.emit(1.5)
    assert status(window).rate == 1.5
    assert window.player.controls.speed_button.text() == rate_label(1.5)
    window.open_path("mock://other")  # a new file starts at normal speed in the UI
    assert window.player.controls.speed_button.text() == rate_label(1.0)


def test_stop_then_play_and_end_then_play(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=3000")
    window.player.stop()
    qtbot.waitUntil(lambda: status(window).state is S.READY)
    assert window.player.message[1].startswith("Stopped")
    window.player.toggle_play_pause()
    qtbot.waitUntil(lambda: status(window).state is S.PLAYING)
    engine_of(window).advance(5_000)
    qtbot.waitUntil(lambda: status(window).state is S.ENDED)
    window.player.toggle_play_pause()
    assert status(window).state is S.PLAYING and status(window).position_ms == 0


def test_open_failure_shows_error_page(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://broken?fail=open")
    qtbot.waitUntil(lambda: window.player.message[0] == USER_MESSAGES[ErrorCode.MEDIA_OPEN_FAILED])
    assert not window.player.controls.play_button.isEnabled()
    assert not window.player._message_action.isHidden()
    assert window.windowTitle() == PRODUCT_NAME
    window.open_path("mock://clip")
    qtbot.waitUntil(lambda: status(window).state is S.PLAYING)


def test_missing_file_is_reported(window: MainWindow, tmp_path: Path) -> None:
    window.open_path(str(tmp_path / "nope.mkv"))
    assert window.player.message[0] == USER_MESSAGES[ErrorCode.MEDIA_NOT_FOUND]


# ------------------------------------------------------------- fullscreen
def test_fullscreen_hides_chrome_and_restores(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    window.toggle_fullscreen()
    qtbot.waitUntil(window.isFullScreen)
    assert window._rail.isHidden() and window.menuBar().isHidden() and window.statusBar().isHidden()
    assert window.player.controls.fullscreen_button.accessibleName() == "Exit fullscreen"
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not window.isFullScreen())
    assert not window._rail.isHidden() and not window.menuBar().isHidden()


def test_fullscreen_returns_to_maximized(window: MainWindow, qtbot: QtBot) -> None:
    window.showMaximized()
    qtbot.waitUntil(window.isMaximized)
    window.toggle_fullscreen()
    qtbot.waitUntil(window.isFullScreen)
    window.exit_fullscreen()
    qtbot.waitUntil(window.isMaximized)


def test_leaving_player_page_exits_fullscreen(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    window.toggle_fullscreen()
    qtbot.waitUntil(window.isFullScreen)
    window.show_page(window.settings)
    qtbot.waitUntil(lambda: not window.isFullScreen())


def test_double_click_on_video_toggles_fullscreen(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    qtbot.mouseDClick(window.player.video, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(window.isFullScreen)
    window.exit_fullscreen()


class FakeCursor:
    position = QPoint(10, 10)

    @classmethod
    def pos(cls) -> QPoint:
        return cls.position


def test_controls_auto_hide_while_playing(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pages.player, "QCursor", FakeCursor)
    window.player.set_preferences(replace(Preferences(), controls_hide_delay_ms=1000))
    window.open_path("mock://clip")
    window.player.set_fullscreen_mode(True)  # no real fullscreen needed for the timing logic
    for _ in range(6):  # 6 x 200 ms of no movement
        window.player._poll_cursor()
    assert window.player.controls_hidden
    FakeCursor.position = QPoint(50, 60)  # mouse moved
    window.player._poll_cursor()
    assert not window.player.controls_hidden
    window.player.toggle_play_pause()  # paused: controls must stay
    for _ in range(10):
        window.player._poll_cursor()
    assert not window.player.controls_hidden
    window.player.set_fullscreen_mode(False)


def test_start_fullscreen_preference(qtbot: QtBot, store: PreferencesStore) -> None:
    store.save(replace(Preferences(), start_fullscreen=True))
    win = make_window(qtbot, store)
    win.open_path("mock://clip")
    qtbot.waitUntil(win.isFullScreen)
    win.close()


# ------------------------------------------------------------- responsive
@pytest.mark.parametrize(
    ("width", "stop", "volume", "speed", "skip"),
    [
        (COMPACT_WIDTH + 200, True, True, True, True),
        (COMPACT_WIDTH - 10, False, False, True, True),
        (NARROW_WIDTH - 10, False, False, False, False),
    ],
)
def test_control_bar_breakpoints(
    window: MainWindow, width: int, stop: bool, volume: bool, speed: bool, skip: bool
) -> None:
    c = window.player.controls
    c.apply_width(width)
    assert c.stop_button.isHidden() is not stop
    assert c.volume.isHidden() is not volume
    assert c.speed_button.isHidden() is not speed
    assert c.back_button.isHidden() is not skip
    assert not c.play_button.isHidden() and not c.fullscreen_button.isHidden() and not c.seek.isHidden()


def test_window_resizes_to_minimum_without_errors(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    window.resize(window.minimumSize())
    qtbot.wait(50)
    assert window.width() >= window.minimumWidth()


# ------------------------------------------------------------ preferences
def test_saved_volume_is_applied_to_engine(qtbot: QtBot, store: PreferencesStore) -> None:
    store.save(replace(Preferences(), volume=33, muted=True))
    win = make_window(qtbot, store)
    assert status(win).volume == 33 and status(win).muted is True
    assert win.player.controls.volume.value() == 33
    win.close()


def test_close_saves_volume_and_geometry(window: MainWindow, store: PreferencesStore) -> None:
    window.show_page(window.player)
    window.player.controls.volume.setValue(45)
    window.close()
    saved = store.load()
    assert saved.volume == 45
    assert saved.window is not None and saved.window.width >= window.minimumWidth()


def test_volume_not_saved_when_remember_is_off(qtbot: QtBot, store: PreferencesStore) -> None:
    store.save(replace(Preferences(), volume=70, remember_volume=False))
    win = make_window(qtbot, store)
    win.player.controls.volume.setValue(10)
    win.close()
    assert store.load().volume == 70


def test_settings_changes_are_saved_immediately(window: MainWindow, store: PreferencesStore) -> None:
    window.settings.hide_delay.setValue(5)
    window.settings.start_fullscreen.setChecked(True)
    saved = store.load()
    assert saved.controls_hide_delay_ms == 5000 and saved.start_fullscreen is True
    window.settings.reset_button.click()
    assert store.load().controls_hide_delay_ms == Preferences().controls_hide_delay_ms


def test_offscreen_geometry_is_ignored(qtbot: QtBot, store: PreferencesStore) -> None:
    store.save(replace(Preferences(), window=WindowGeometry(-50_000, -50_000, 900, 600)))
    win = make_window(qtbot, store, start=False)
    assert win.x() > -10_000
    win.close()


# ---------------------------------------------------------- accessibility
def test_every_control_has_an_accessible_name(window: MainWindow) -> None:
    controls: list[QWidget] = [*window.findChildren(QAbstractButton), *window.findChildren(QSlider)]
    unnamed = [w for w in controls if w.isVisibleTo(window) and not (w.accessibleName() or w.text())]  # type: ignore[attr-defined]
    assert not unnamed, [type(w).__name__ for w in unnamed]


def test_settings_controls_are_keyboard_reachable(window: MainWindow) -> None:
    s = window.settings
    for widget in (s.seek_step, s.remember_volume, s.hide_delay, s.start_fullscreen, s.reset_button):
        assert widget.focusPolicy() & Qt.FocusPolicy.TabFocus


# --------------------------------------------------------------- lifecycle
def test_close_shuts_engine_down_before_window(window: MainWindow) -> None:
    engine = engine_of(window)
    window.open_path("mock://clip")
    alive: list[bool] = []
    original = engine._do_close

    def spy() -> None:
        alive.append(window.isVisible())
        original()

    engine._do_close = spy  # type: ignore[method-assign]
    window.close()
    assert engine.state is S.CLOSED
    assert alive == [True]


def test_bridge_delivers_on_ui_thread(qtbot: QtBot) -> None:
    bridge = UiBridge()
    seen: list[tuple[object, bool]] = []
    main = threading.current_thread()
    bridge.delivered.connect(lambda p: seen.append((p, threading.current_thread() is main)))
    worker = threading.Thread(target=lambda: bridge.post("hello"))
    worker.start()
    worker.join()
    qtbot.waitUntil(lambda: bool(seen), timeout=2000)
    assert seen == [("hello", True)]


@pytest.mark.parametrize("ms", [0, 59_999, 3_600_000, 3_723_000, None])
def test_format_time(ms: int | None) -> None:
    expected = {0: "00:00", 59_999: "00:59", 3_600_000: "1:00:00", 3_723_000: "1:02:03", None: "--:--"}
    assert format_time(ms) == expected[ms]


def _run_app(args: list[str], config_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "BABARIFY_CONFIG_DIR": str(config_dir)}  # never touch the user's settings
    return subprocess.run(
        [sys.executable, "-m", "babarify_frame", *args], capture_output=True, text=True, timeout=60, env=env
    )


def test_app_starts_and_exits_cleanly(tmp_path: Path) -> None:
    proc = _run_app(["--engine", "mock", "--smoke-test", "800"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "exited cleanly with code 0" in proc.stderr
    assert (tmp_path / "Babarify" / "Frame" / "settings.json").exists()


@pytest.mark.integration
def test_real_app_plays_file_and_exits_cleanly(tmp_path: Path) -> None:
    media = MEDIA / "h264_1080p30_aac.mp4"
    if not media.exists():
        pytest.skip("generated media missing: run tools/engine-benchmark/make_media.py")
    proc = _run_app([str(media), "--smoke-test", "3000"], tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "exited cleanly with code 0" in proc.stderr


# --------------------------------------------------------------------- M4
def test_hardware_setting_restarts_engine_and_resumes(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    window.player.seek_to(25_000)
    first = engine_of(window)
    assert first.options.hardware_decoding is True
    window.show_page(window.settings)
    window.settings.hardware_decoding.setCurrentIndex(1)  # Off
    qtbot.waitUntil(
        lambda: window.player.engine_is_ready and window.controller.engine is not first, timeout=5000
    )
    second = engine_of(window)
    assert first.state is S.CLOSED
    assert second.options.hardware_decoding is False
    assert window.controller.capabilities().engine_name == "mock"
    qtbot.waitUntil(lambda: status(window).state is S.PLAYING and status(window).position_ms == 25_000)
    assert status(window).uri == "mock://clip?duration=60000"
    assert window.current_page() is window.settings  # the change did not navigate away


def test_hardware_setting_is_persisted(window: MainWindow, store: PreferencesStore) -> None:
    window.settings.hardware_decoding.setCurrentIndex(1)
    assert store.load().hardware_decoding is False


def test_playback_info_panel(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    dialog = window.show_playback_info()
    qtbot.waitUntil(dialog.isVisible)
    rows, _log = dialog.snapshot()
    assert rows["Engine"] == "mock"
    assert rows["State"] == "playing"
    assert rows["Video"].startswith("h264")
    assert rows["Decoder"] == "software (simulated)"
    assert rows["Hardware decoding setting"] == "unavailable"
    dialog.copy_to_clipboard()
    from PySide6.QtGui import QGuiApplication

    text = QGuiApplication.clipboard().text()
    assert "Decoder" in text and "Recent engine log:" in text
    window.open_path("mock://broken?fail=open")
    qtbot.waitUntil(lambda: dialog.snapshot()[0]["Last error"].startswith("media_open_failed"))
    dialog.close()


def test_playback_info_without_engine(qtbot: QtBot, store: PreferencesStore) -> None:
    win = make_window(qtbot, store, start=False)
    rows, log = win.show_playback_info().snapshot()
    assert rows == {"Engine": "not running"} and log == []
    win.close()
