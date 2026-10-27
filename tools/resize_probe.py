"""Which part of the window makes a large resize slow? (M4 investigation of M3 finding A1 / R19.)

Measures growing the window from 900x600 to 1400x860 (median of 8) for one variant:
  full          the real window (mock engine; no media)
  no-native     VideoSurface without its native child window
  no-rail       navigation rail hidden
  no-chrome     menu bar and status bar hidden
  plain-style   global "*" stylesheet rule narrowed to QWidget
  bare          bare QMainWindow with a label (Qt floor)
Usage:  python tools/resize_probe.py <variant> [page]
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QWidget

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui import theme
from babarify_frame.ui.pages import player as player_page


def measure(app: QApplication, window: QWidget) -> tuple[float, float]:
    grow = []
    for _ in range(8):
        window.resize(900, 600)
        app.processEvents()
        time.sleep(0.05)
        t = time.perf_counter()
        window.resize(1400, 860)
        app.processEvents()
        grow.append((time.perf_counter() - t) * 1000)
        time.sleep(0.05)
    return statistics.median(grow), max(grow)


def main() -> int:
    variant = sys.argv[1]
    page = sys.argv[2] if len(sys.argv) > 2 else "player"
    app = QApplication(sys.argv[:1])
    sheet = theme.STYLESHEET
    if variant == "plain-style":
        sheet = sheet.replace("* {", "QWidget {", 1)
    if variant == "no-native":

        class PlainSurface(QWidget):
            double_clicked = player_page.VideoSurface.double_clicked

        player_page.VideoSurface = PlainSurface  # type: ignore[misc, assignment]
    if variant == "bare":
        window: QWidget = QMainWindow()
        window.setCentralWidget(QLabel("bare"))  # type: ignore[attr-defined]
    else:
        app.setStyleSheet(sheet)
        from babarify_frame.ui.app import load_icon
        from babarify_frame.ui.main_window import MainWindow

        factory = EngineFactory()
        factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True)))
        store = PreferencesStore(Path(tempfile.mkdtemp()) / "s.json")
        main_window = MainWindow(factory, load_icon(), engine_name="mock", store=store)
        main_window.start_engine()
        while not main_window.player.engine_is_ready:
            app.processEvents()
        main_window.show_page(
            {"player": main_window.player, "home": main_window.home, "settings": main_window.settings}[page]
        )
        if variant == "no-rail":
            main_window._rail.hide()
        if variant == "no-chrome":
            main_window.menuBar().hide()
            main_window.statusBar().hide()
        window = main_window
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
    window.show()
    for _ in range(30):
        app.processEvents()
        time.sleep(0.01)
    median, worst = measure(app, window)
    print(
        f"{variant:12} page={page:8} grow 900x600 -> 1400x860: median {median:6.1f} ms, max {worst:6.1f} ms"
    )
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
