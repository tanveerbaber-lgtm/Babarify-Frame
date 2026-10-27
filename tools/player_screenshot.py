"""Capture evidence screenshots of the real player: home, playback, responsive, fullscreen, states.

Screen-grabs the window region so Direct3D video output is included (QWidget.grab cannot see it).
Uses a throw-away settings folder so the user's real preferences are never touched.
Usage:  python tools/player_screenshot.py docs/milestones/M3/evidence
"""

from __future__ import annotations

import ctypes
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.theme import STYLESHEET

MEDIA = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "media" / "generated"


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def wait(app: QApplication, window: MainWindow, *states: S, timeout: float = 15) -> S:
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        app.processEvents()
        if window.controller.engine_name and window.controller.status().state in states:
            return window.controller.status().state
        time.sleep(0.01)
    raise TimeoutError(f"waited for {states}")


def _owned_by(window: MainWindow) -> bool:
    """True if every sampled point of the window's area belongs to this window on screen.

    The capture reads screen pixels, so anything covering the window would be recorded.
    Never save a screenshot that might contain another application's content.
    """
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = wintypes.HWND
    ratio = window.devicePixelRatio()
    geo = window.frameGeometry()
    own = int(window.winId())
    for fx in (0.05, 0.5, 0.95):
        for fy in (0.1, 0.5, 0.9):
            x = int((geo.x() + geo.width() * fx) * ratio)
            y = int((geo.y() + geo.height() * fy) * ratio)
            hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
            root = user32.GetAncestor(hwnd, 2) if hwnd else None  # GA_ROOT
            if not root or int(root) != own:
                return False
    return True


def grab(app: QApplication, window: MainWindow, path: Path) -> None:
    window.raise_()
    window.activateWindow()
    pump(app, 0.5)
    if not _owned_by(window):
        print(f"NOT saved {path}: another window covers the player", file=sys.stderr)
        return
    geo = window.frameGeometry()
    shot = window.screen().grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height())
    shot.save(str(path))
    print(
        f"saved {path} ({shot.width()}x{shot.height()}) state={window.controller.status().state.value} "
        f"status='{window.statusBar().currentMessage()}'"
    )


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    config = Path(tempfile.mkdtemp(prefix="babarify-shots-")) / "settings.json"
    window = MainWindow(default_factory(), load_icon(), store=PreferencesStore(config))
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)  # capture only our own pixels
    window.resize(1180, 740)
    window.show()
    window.start_engine()
    wait(app, window, S.READY)
    grab(app, window, out / "home.png")

    window.show_page(window.settings)
    grab(app, window, out / "settings.png")

    window.open_path(str(MEDIA / "h264_1080p30_aac.mp4"))
    wait(app, window, S.PLAYING)
    pump(app, 2.5)
    grab(app, window, out / "playing.png")

    window.resize(640, 480)
    pump(app, 1.0)
    grab(app, window, out / "playing_narrow.png")
    window.resize(1180, 740)
    pump(app, 0.5)

    window.toggle_fullscreen()
    pump(app, 1.0)
    grab(app, window, out / "fullscreen_controls.png")
    pump(app, 4.0)  # longer than the default 3 s auto-hide delay, mouse untouched
    print(f"controls hidden after idle: {window.player.controls_hidden}")
    grab(app, window, out / "fullscreen_idle.png")
    window.exit_fullscreen()
    pump(app, 0.8)

    window.open_path(str(MEDIA / "c_audio_flac.flac"))
    wait(app, window, S.PLAYING)
    pump(app, 1.5)
    grab(app, window, out / "audio_only.png")

    window.open_path(str(MEDIA / "truncated.mp4"))
    wait(app, window, S.ERROR)
    grab(app, window, out / "error.png")

    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
