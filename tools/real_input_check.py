"""Verify real mouse input over live libVLC video (M3 evidence): double-click toggles fullscreen,
idle hides the controls, mouse movement brings them back.

This sends REAL mouse input (SendInput) and briefly moves the cursor, then restores it.
Safety: before every click it asks Windows which top-level window owns the target point and
aborts unless it is the Babarify Frame window, so it can never click into another app.
Uses a throw-away settings folder.

Usage:  python tools/real_input_check.py
"""

from __future__ import annotations

import ctypes
import json
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.theme import STYLESHEET

MEDIA = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "media" / "generated"
user32 = ctypes.windll.user32
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wintypes.HWND
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004


class SafetyAbort(RuntimeError):
    pass


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_until(app: QApplication, check: object, timeout: float) -> bool:
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        app.processEvents()
        if callable(check) and check():
            return True
        time.sleep(0.01)
    return False


def physical_center(window: MainWindow) -> tuple[int, int]:
    video = window.player.video
    centre = video.mapToGlobal(QPoint(video.width() // 2, video.height() // 2))
    ratio = video.devicePixelRatio()
    return int(centre.x() * ratio), int(centre.y() * ratio)


def assert_owned(window: MainWindow, x: int, y: int) -> None:
    hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
    root = user32.GetAncestor(hwnd, 2) if hwnd else None  # GA_ROOT
    if not root or int(root) != int(window.winId()):
        raise SafetyAbort(f"point ({x},{y}) does not belong to the player window; no input sent")


def double_click(app: QApplication, window: MainWindow) -> None:
    x, y = physical_center(window)
    assert_owned(window, x, y)
    user32.SetCursorPos(x, y)
    pump(app, 0.15)
    assert_owned(window, x, y)
    for _ in range(2):
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.05)


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    store = PreferencesStore(Path(tempfile.mkdtemp(prefix="babarify-input-")) / "settings.json")
    store.save(replace(Preferences(), controls_hide_delay_ms=1000))
    window = MainWindow(default_factory(), load_icon(), store=store)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.resize(1180, 740)
    window.show()
    window.raise_()
    window.activateWindow()
    window.start_engine()
    wait_until(app, lambda: window.player.engine_is_ready, 15)
    window.open_path(str(MEDIA / "h264_1080p30_aac.mp4"))
    wait_until(app, lambda: window.controller.status().state is S.PLAYING, 15)
    pump(app, 1.0)

    saved = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(saved))
    results: dict[str, object] = {}
    try:
        double_click(app, window)
        results["double_click_enters_fullscreen"] = wait_until(app, window.isFullScreen, 3)
        pump(app, 0.5)
        x, y = physical_center(window)
        user32.SetCursorPos(x, y)
        pump(app, 0.3)  # let the player register the cursor position, then keep it still
        results["controls_hide_when_idle"] = wait_until(app, lambda: window.player.controls_hidden, 3)
        user32.SetCursorPos(x + 40, y + 25)
        results["mouse_move_shows_controls"] = wait_until(app, lambda: not window.player.controls_hidden, 1.5)
        pump(app, 0.3)
        double_click(app, window)
        results["double_click_exits_fullscreen"] = wait_until(app, lambda: not window.isFullScreen(), 3)
    except SafetyAbort as exc:
        results["aborted"] = str(exc)
    finally:
        user32.SetCursorPos(saved.x, saved.y)
        window.close()
        app.processEvents()
    results["pass"] = all(v is True for k, v in results.items() if k != "pass")
    print(json.dumps(results, indent=2))
    return 0 if results["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
