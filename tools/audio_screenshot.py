"""Capture the real player's audio screen with each animation, and with a song's own picture.

Uses a throw-away settings folder so the user's real preferences are never touched.
Usage:  python tools/audio_screenshot.py <output folder> <song without a picture> <song with a picture>
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.core.music import STYLE_CYCLE
from babarify_frame.playback.factory import default_factory
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.theme import STYLESHEET


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_playing(app: QApplication, window: MainWindow, timeout: float = 30) -> None:
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        app.processEvents()
        if window.controller.engine_name and window.controller.status().state is S.PLAYING:
            return
        time.sleep(0.01)
    raise TimeoutError("the song didn't start")


def main() -> None:
    out = Path(sys.argv[1])
    plain, covered = sys.argv[2], sys.argv[3]
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    with tempfile.TemporaryDirectory() as folder:
        store = PreferencesStore(Path(folder) / "settings.json")
        window = MainWindow(default_factory(), load_icon(), engine_name="libvlc", store=store)
        window.resize(1280, 800)
        window.show()
        window.start_engine()
        pump(app, 3)
        window.player.open_path(plain)
        wait_playing(app, window)
        window.show_page(window.player)
        for style in STYLE_CYCLE:
            window._choose_animation(style)
            pump(app, 2.5)
            window.grab().save(str(out / f"style_{style.value}.png"))
            visualizer = window.player.audio_view.visualizer
            started = time.perf_counter()
            for _ in range(10):
                visualizer.grab()
            cost = (time.perf_counter() - started) * 100
            size = f"{visualizer.width()}x{visualizer.height()}"
            print(f"{style.value}: shown {visualizer.shown_style.value}, about {cost:.1f} ms at {size}")
        window.player.play_queue([covered, plain])
        wait_playing(app, window)
        pump(app, 2)
        view = window.player.audio_view
        print(f"picture shown: {view.showing_picture}")
        print(f"title: {view.title.text()!r}; artist: {view.artist.text()!r}")
        print(f"stage is the audio screen: {window.player._stage.currentWidget() is view}")
        window.grab().save(str(out / "with_picture.png"))
        window.player.stop()
        pump(app, 1)
        window.close()
        pump(app, 1)


if __name__ == "__main__":
    main()
