"""Measure UI event-loop responsiveness of the real app during playback (M3 evidence).

A precise 16 ms Qt timer records how late each tick fires (lateness = actual interval - 16 ms)
while the real libVLC engine plays 4K HEVC and the script drives typical interaction:
window resizes, page switches, seeks, and a fullscreen round trip. An idle run (no media)
gives the measurement floor.

Thresholds were fixed before the first run (see docs/milestones/M3/acceptance-report.md):
  p95 lateness <= 16 ms (never more than one 60 Hz frame late)
  max lateness <= 100 ms (below a perceptible pause)

Usage:  python tools/ui_responsiveness.py
Uses a throw-away settings folder; the user's preferences are not touched.
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.theme import STYLESHEET

MEDIA = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "media" / "generated"
TICK_MS = 16
P95_LIMIT_MS = 16.0
MAX_LIMIT_MS = 100.0


class LagProbe:
    def __init__(self) -> None:
        self.samples: list[float] = []
        self._last = 0.0
        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.samples.clear()
        self._last = time.perf_counter()
        self.timer.start()

    def stop(self) -> dict[str, float]:
        self.timer.stop()
        s = sorted(self.samples)
        return {
            "ticks": len(s),
            "p50_ms": round(statistics.median(s), 2),
            "p95_ms": round(s[int(len(s) * 0.95) - 1], 2),
            "p99_ms": round(s[int(len(s) * 0.99) - 1], 2),
            "max_ms": round(s[-1], 2),
        }

    def _tick(self) -> None:
        now = time.perf_counter()
        self.samples.append(max(0.0, (now - self._last) * 1000 - TICK_MS))
        self._last = now


def run_for(app: QApplication, seconds: float, step: object = None) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        if callable(step):
            step()
        time.sleep(0.001)


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    store = PreferencesStore(Path(tempfile.mkdtemp(prefix="babarify-resp-")) / "settings.json")
    window = MainWindow(default_factory(), load_icon(), store=store)
    window.resize(1180, 740)
    window.show()
    window.start_engine()
    probe = LagProbe()
    end = time.perf_counter() + 15
    while not window.player.engine_is_ready and time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)

    results: dict[str, dict[str, float]] = {}
    probe.start()
    run_for(app, 8)
    results["idle"] = probe.stop()

    window.open_path(str(MEDIA / "hevc_2160p30_aac.mkv"))
    end = time.perf_counter() + 15
    while window.controller.status().state is not S.PLAYING and time.perf_counter() < end:
        app.processEvents()
    run_for(app, 1.0)
    probe.start()
    run_for(app, 8)
    results["playing_4k_hevc"] = probe.stop()

    sizes = [(900, 600), (1400, 860), (700, 480), (1180, 740)]
    actions = [
        ("resize 900x600", lambda: window.resize(*sizes[0])),
        ("seek 5 s", lambda: window.player.seek_to(5_000)),
        ("page: settings", lambda: window.show_page(window.settings)),
        ("resize 1400x860", lambda: window.resize(*sizes[1])),
        ("page: player", lambda: window.show_page(window.player)),
        ("seek 12 s", lambda: window.player.seek_to(12_000)),
        ("resize 700x480", lambda: window.resize(*sizes[2])),
        ("enter fullscreen", lambda: window.toggle_fullscreen()),
        ("exit fullscreen", lambda: window.exit_fullscreen()),
        ("resize 1180x740", lambda: window.resize(*sizes[3])),
        ("pause", lambda: window.player.toggle_play_pause()),
        ("play", lambda: window.player.toggle_play_pause()),
    ]
    per_action: dict[str, float] = {}
    probe.start()
    for name, action in actions:
        before = len(probe.samples)
        action()
        run_for(app, 0.6)
        per_action[name] = round(max(probe.samples[before:], default=0.0), 1)
    results["playing_with_interaction"] = probe.stop()

    window.close()
    app.processEvents()
    verdict = all(
        r["p95_ms"] <= P95_LIMIT_MS and r["max_ms"] <= MAX_LIMIT_MS for k, r in results.items() if k != "idle"
    )
    print(
        json.dumps(
            {
                "thresholds": {"p95_ms": P95_LIMIT_MS, "max_ms": MAX_LIMIT_MS},
                "results": results,
                "max_lag_per_action_ms": per_action,
                "pass": verdict,
            },
            indent=2,
        )
    )
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
