"""Player window tests against the deterministic mock engine (plus one real-app smoke test)."""

from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from babarify_frame import PRODUCT_NAME, TAGLINE
from babarify_frame.core.errors import USER_MESSAGES, ErrorCode
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.widgets import format_time

pytestmark = pytest.mark.ui

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "generated"


def mock_factory() -> EngineFactory:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    return factory


def broken_factory() -> EngineFactory:
    def fail() -> PlaybackEngine:
        raise OSError("libvlc.dll not found")

    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", fail, lambda: EngineProbe("mock", False)))
    return factory


@pytest.fixture
def window(qtbot: QtBot) -> Iterator[MainWindow]:
    win = MainWindow(mock_factory(), load_icon(), engine_name="mock")
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.controller.engine_name == "mock", timeout=5000)
    yield win
    win.close()


def engine_of(window: MainWindow) -> MockEngine:
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    return engine


def labels(window: MainWindow) -> set[str]:
    return {label.text() for label in window.findChildren(QLabel)}


def test_branding(window: MainWindow) -> None:
    assert window.windowTitle() == PRODUCT_NAME
    assert not window.windowIcon().isNull()
    assert {PRODUCT_NAME, TAGLINE} <= labels(window)


def test_icon_resources_exist() -> None:
    icon = load_icon()
    assert {s.width() for s in icon.availableSizes()} >= {16, 32, 256}


def test_engine_ready_enables_open_only(window: MainWindow) -> None:
    assert window.open_action.isEnabled()
    assert not window.play_action.isEnabled()
    assert not window.stop_action.isEnabled()
    assert not window.forward_action.isEnabled()
    assert "Open a file to start" in labels(window)


def test_engine_unavailable_is_reported(qtbot: QtBot) -> None:
    win = MainWindow(broken_factory(), load_icon(), engine_name="mock")
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: "Playback engine unavailable" in labels(win), timeout=5000)
    assert USER_MESSAGES[ErrorCode.ENGINE_UNAVAILABLE] in "\n".join(labels(win))
    assert not win.open_action.isEnabled()
    assert not win.play_action.isEnabled()
    win.close()


def test_file_opened_before_engine_ready_is_opened_afterwards(qtbot: QtBot) -> None:
    win = MainWindow(mock_factory(), load_icon(), engine_name="mock")
    qtbot.addWidget(win)
    win.show()
    win.open_path("mock://early?duration=5000")  # e.g. a file passed on the command line
    win.start_engine()
    qtbot.waitUntil(lambda: win.controller.engine_name == "mock", timeout=5000)
    assert win.controller.status().state is S.PLAYING
    assert win.controller.status().uri == "mock://early?duration=5000"
    win.close()


def test_open_enables_controls_and_shows_title(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    qtbot.waitUntil(lambda: window.play_action.isEnabled() and window.forward_action.isEnabled())
    assert window.stop_action.isEnabled()
    assert "mock://clip" in window.windowTitle()


def test_space_toggles_play_pause(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    qtbot.keyClick(window, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: window.controller.status().state is S.PAUSED)
    qtbot.keyClick(window, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: window.controller.status().state is S.PLAYING)


def test_position_display_follows_engine(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    engine_of(window).advance(12_000)
    qtbot.waitUntil(lambda: window._time_label.text() == format_time(12_000), timeout=2000)
    assert window._seek.value() == 12_000
    assert window._duration_label.text() == format_time(60_000)


def test_seek_and_relative_seek_are_clamped(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    window.seek_to(30_000)
    assert window.controller.status().position_ms == 30_000
    window.seek_relative(-50_000)
    assert window.controller.status().position_ms == 0
    window.seek_to(90_000)
    assert window.controller.status().position_ms == 60_000
    qtbot.keyClick(window, Qt.Key.Key_Left)  # at 60 s; -5 s
    assert window.controller.status().position_ms == 55_000


def test_slider_click_requests_seek(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    window._seek.seek_requested.emit(20_000)
    assert window.controller.status().position_ms == 20_000


def test_volume_and_mute(window: MainWindow, qtbot: QtBot) -> None:
    window._volume.setValue(40)
    assert window.controller.status().volume == 40
    qtbot.keyClick(window, Qt.Key.Key_Down)
    assert window.controller.status().volume == 35
    qtbot.keyClick(window, Qt.Key.Key_M)
    assert window.controller.status().muted is True
    window._volume.setValue(50)  # raising the volume unmutes
    assert window.controller.status().muted is False


def test_stop_then_play_restarts(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=60000")
    engine_of(window).advance(5_000)
    window.stop()
    qtbot.waitUntil(lambda: window.controller.status().state is S.READY)
    assert window.play_action.isEnabled()
    window.toggle_play_pause()
    qtbot.waitUntil(lambda: window.controller.status().state is S.PLAYING)


def test_ended_then_play_restarts(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip?duration=3000")
    engine_of(window).advance(5_000)
    qtbot.waitUntil(lambda: window.controller.status().state is S.ENDED)
    window.toggle_play_pause()
    assert window.controller.status().state is S.PLAYING
    assert window.controller.status().position_ms == 0


def test_open_failure_shows_message_and_disables_play(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://broken?fail=open")
    qtbot.waitUntil(lambda: USER_MESSAGES[ErrorCode.MEDIA_OPEN_FAILED] in labels(window))
    assert not window.play_action.isEnabled()
    assert window.windowTitle() == PRODUCT_NAME
    # The player recovers with the next file.
    window.open_path("mock://clip")
    qtbot.waitUntil(lambda: window.controller.status().state is S.PLAYING)


def test_missing_file_is_reported(window: MainWindow, tmp_path: Path, qtbot: QtBot) -> None:
    window.open_path(str(tmp_path / "nope.mkv"))
    assert USER_MESSAGES[ErrorCode.MEDIA_NOT_FOUND] in labels(window)


def test_fullscreen_toggle_hides_chrome(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    window.toggle_fullscreen()
    qtbot.waitUntil(window.isFullScreen)
    assert not window._header.isVisible()
    assert not window.menuBar().isVisible()
    assert window._controls.isVisible()
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not window.isFullScreen())
    assert window._header.isVisible()


def test_double_click_on_video_toggles_fullscreen(window: MainWindow, qtbot: QtBot) -> None:
    window.open_path("mock://clip")
    qtbot.mouseDClick(window._video, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(window.isFullScreen)
    window.exit_fullscreen()


def test_close_shuts_engine_down_before_window(qtbot: QtBot) -> None:
    win = MainWindow(mock_factory(), load_icon(), engine_name="mock")
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.controller.engine_name == "mock", timeout=5000)
    engine = engine_of(win)
    win.open_path("mock://clip")
    window_alive_when_engine_closed: list[bool] = []
    original = engine._do_close

    def spy() -> None:
        window_alive_when_engine_closed.append(win.isVisible())
        original()

    engine._do_close = spy  # type: ignore[method-assign]
    win.close()
    assert engine.state is S.CLOSED
    assert window_alive_when_engine_closed == [True]


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


def test_app_starts_and_exits_cleanly() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "babarify_frame", "--engine", "mock", "--smoke-test", "800"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "exited cleanly with code 0" in proc.stderr


@pytest.mark.integration
def test_real_app_plays_file_and_exits_cleanly() -> None:
    media = MEDIA / "h264_1080p30_aac.mp4"
    if not media.exists():
        pytest.skip("generated media missing: run tools/engine-benchmark/make_media.py")
    proc = subprocess.run(
        [sys.executable, "-m", "babarify_frame", str(media), "--smoke-test", "3000"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "exited cleanly with code 0" in proc.stderr
