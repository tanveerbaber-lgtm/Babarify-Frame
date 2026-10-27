"""Capture the M1 shell window to a PNG after engine probes finish (evidence for milestone reports).

Usage:  python tools/shell_screenshot.py docs/milestones/M1/evidence/shell.png
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from babarify_frame.playback.factory import default_factory
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import CANDIDATE_ENGINES, MainWindow
from babarify_frame.ui.theme import STYLESHEET


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shell.png")
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(default_factory(), load_icon())
    window.resize(1100, 700)
    window.show()
    started = time.perf_counter()
    window.start_engine_probes()
    while len(window.probe_results) < len(CANDIDATE_ENGINES) and time.perf_counter() - started < 20:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    out.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(out))
    for name, result in window.probe_results.items():
        print(f"{name}: available={result.available} version={result.version} detail={result.detail}")
    print(f"probes finished in {time.perf_counter() - started:.2f}s; saved {out}")
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
