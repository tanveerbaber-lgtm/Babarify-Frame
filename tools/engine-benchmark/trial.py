"""Run ONE benchmark scenario for ONE engine in this (fresh) process and print a JSON result.

Invoked by bench.py; can be run by hand for debugging:
    python tools/engine-benchmark/trial.py --engine mpv --scenario perf --media h264_1080p30_aac.mp4

Video renders into a real 1280x720 Qt window (the same embedding path the app
will use). Audio goes to the default output; the test tone is -60 dB.

Measurement notes:
* Times are wall-clock (time.perf_counter) taken inside engine event callbacks.
* Engines report state differently (libVLC's "Playing" fires before the first
  frame; its position jumps to a seek target immediately), so the comparable
  metrics are progress-based:
    open_to_progress_ms = time until reported position >= 500 ms, minus 500 ms
    seek_resume_ms      = time until position >= target + 500 ms, minus 500 ms
  i.e. how long until playback is demonstrably moving again. They are
  estimates bounded by each engine's position-report interval, not
  photon-on-screen measurements. The raw engine-reported values are kept too.
* CPU = this process's user+system CPU time / wall time, as % of ONE logical core.
  GPU load is not measured.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil
from PySide6.QtWidgets import QApplication, QWidget

from babarify_frame.core.events import ErrorOccurred, PlaybackEvent, PositionChanged, StateChanged
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory

MEDIA_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "media" / "generated"
OPEN_TIMEOUT = 15.0
PROGRESS_MS = 500


class Recorder:
    """Collects timestamped engine events and waits for conditions while pumping Qt."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.events: list[tuple[float, PlaybackEvent]] = []
        self.lock = threading.Lock()

    def __call__(self, event: PlaybackEvent) -> None:
        with self.lock:
            self.events.append((time.perf_counter(), event))

    def mark(self) -> int:
        with self.lock:
            return len(self.events)

    def wait_for(self, since: int, match: Callable[[PlaybackEvent], bool], timeout: float) -> float | None:
        """Return the timestamp of the first matching event after index ``since``, or None on timeout."""
        deadline = time.perf_counter() + timeout
        while True:
            with self.lock:
                for t, ev in self.events[since:]:
                    if match(ev):
                        return t
            if time.perf_counter() > deadline:
                return None
            self.app.processEvents()
            time.sleep(0.003)

    def pump(self, seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            self.app.processEvents()
            time.sleep(0.005)


def is_state(*states: S) -> Callable[[PlaybackEvent], bool]:
    return lambda ev: isinstance(ev, StateChanged) and ev.new in states


def cpu_seconds(proc: psutil.Process) -> float:
    t = proc.cpu_times()
    return float(t.user + t.system)


def setup(engine_name: str) -> tuple[QApplication, QWidget, Any, Recorder, dict[str, float]]:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    assert isinstance(app, QApplication)
    window = QWidget()
    window.setWindowTitle(f"Babarify Frame benchmark — {engine_name}")
    window.resize(1280, 720)
    window.setStyleSheet("background: black;")
    window.show()
    app.processEvents()

    t0 = time.perf_counter()
    engine = default_factory().create(engine_name)  # imports binding, loads DLL, initialises
    t_init = time.perf_counter() - t0
    recorder = Recorder(app)
    engine.subscribe(recorder)
    engine.set_video_output(int(window.winId()))
    return app, window, engine, recorder, {"init_ms": t_init * 1000}


def scenario_perf(engine_name: str, media: str, steady_s: float) -> dict[str, Any]:
    app, window, engine, rec, out = setup(engine_name)
    proc = psutil.Process()
    path = str(MEDIA_DIR / media)

    mark = rec.mark()
    t_open = time.perf_counter()
    engine.open_media(path)
    t_play = rec.wait_for(mark, is_state(S.PLAYING, S.ERROR), OPEN_TIMEOUT)
    if t_play is None or engine.get_playback_state().state is S.ERROR:
        out.update(ok=False, failure="did not reach PLAYING", state=engine.get_playback_state().state.value)
        engine.close()
        return out
    out["open_to_playing_ms"] = (t_play - t_open) * 1000
    t_pos = rec.wait_for(
        mark, lambda ev: isinstance(ev, PositionChanged) and ev.position_ms > 0, OPEN_TIMEOUT
    )
    out["open_to_first_position_ms"] = (t_pos - t_open) * 1000 if t_pos else None
    t_prog = rec.wait_for(
        mark, lambda ev: isinstance(ev, PositionChanged) and ev.position_ms >= PROGRESS_MS, OPEN_TIMEOUT
    )
    out["open_to_progress_ms"] = (t_prog - t_open) * 1000 - PROGRESS_MS if t_prog else None

    rec.pump(1.0)  # settle
    stats_before = getattr(engine, "playback_stats", dict)()
    cpu0, wall0 = cpu_seconds(proc), time.perf_counter()
    rss_samples = []
    while time.perf_counter() - wall0 < steady_s:
        rec.pump(0.5)
        rss_samples.append(proc.memory_info().rss)
    cpu1, wall1 = cpu_seconds(proc), time.perf_counter()
    stats_after = getattr(engine, "playback_stats", dict)()
    out["steady_cpu_pct_one_core"] = 100 * (cpu1 - cpu0) / (wall1 - wall0)
    out["steady_rss_mb_max"] = max(rss_samples) / 2**20
    out["steady_threads"] = proc.num_threads()
    if "dropped" in stats_after:
        out["steady_dropped_frames"] = stats_after["dropped"] - stats_before.get("dropped", 0)
    if "displayed" in stats_after:
        out["steady_displayed_frames"] = stats_after["displayed"] - stats_before.get("displayed", 0)

    duration = engine.get_playback_state().duration_ms or 20_000
    reported, resumed = [], []
    for fraction in (0.25, 0.5, 0.75):
        target = int(duration * fraction)
        mark = rec.mark()
        t_seek = time.perf_counter()
        engine.seek(target)
        t_hit = rec.wait_for(
            mark,
            lambda ev, tgt=target: (
                isinstance(ev, PositionChanged) and tgt - 250 <= ev.position_ms <= tgt + 1500
            ),
            5.0,
        )
        t_res = rec.wait_for(
            mark,
            lambda ev, tgt=target: (
                isinstance(ev, PositionChanged)
                and tgt + PROGRESS_MS <= ev.position_ms <= tgt + PROGRESS_MS + 1500
            ),
            5.0,
        )
        reported.append((t_hit - t_seek) * 1000 if t_hit else None)
        resumed.append((t_res - t_seek) * 1000 - PROGRESS_MS if t_res else None)
        rec.pump(0.5)
    out["seek_reported_ms"] = reported
    out["seek_ms"] = resumed

    info = engine.get_media_info()
    out["media_info"] = (
        {
            "video_codec": info.video_codec,
            "width": info.width,
            "height": info.height,
            "fps": info.frame_rate,
            "audio_codec": info.audio_codec,
        }
        if info
        else None
    )
    out["diagnostics"] = dict(engine.diagnostics())
    out["errors_seen"] = [str(ev.error) for _, ev in rec.events if isinstance(ev, ErrorOccurred)]
    out["rejected_transitions"] = [
        f"{a.value}->{b.value}" for a, b in getattr(engine, "rejected_transitions", [])
    ]

    t_close = time.perf_counter()
    engine.close()
    out["close_ms"] = (time.perf_counter() - t_close) * 1000
    window.close()
    app.processEvents()
    out["ok"] = all(s is not None for s in resumed)
    return out


def scenario_tracks(engine_name: str, media: str) -> dict[str, Any]:
    _app, window, engine, rec, out = setup(engine_name)
    mark = rec.mark()
    engine.open_media(str(MEDIA_DIR / media))
    ok = rec.wait_for(mark, is_state(S.PLAYING), OPEN_TIMEOUT) is not None
    rec.pump(1.5)
    info = engine.get_media_info()
    out["ok"] = ok and info is not None
    if info:
        out["tracks"] = [
            {
                "kind": t.kind.value,
                "id": t.id,
                "codec": t.codec,
                "language": t.language,
                "title": t.title,
                "selected": t.selected,
            }
            for t in info.tracks
        ]
        out["audio_tracks"] = sum(t.kind.value == "audio" for t in info.tracks)
        out["subtitle_tracks"] = sum(t.kind.value == "subtitle" for t in info.tracks)
    engine.close()
    window.close()
    return out


def scenario_errors(engine_name: str) -> dict[str, Any]:
    _app, window, engine, rec, out = setup(engine_name)
    results = {}
    for media in ("not_media.mp4", "truncated.mp4"):
        mark = rec.mark()
        t0 = time.perf_counter()
        engine.open_media(str(MEDIA_DIR / media))
        # Wait for a terminal outcome; transient PLAYING is recorded but not accepted as the result.
        t = rec.wait_for(mark, is_state(S.ERROR, S.ENDED), 5.0)
        rec.pump(0.3)
        final = engine.get_playback_state().state
        results[media] = {
            "outcome": final.value,
            "ms": (t - t0) * 1000 if t else None,
            "states": [ev.new.value for _, ev in rec.events[mark:] if isinstance(ev, StateChanged)],
            "error": next(
                (str(ev.error) for _, ev in rec.events[mark:] if isinstance(ev, ErrorOccurred)), None
            ),
        }
    # The engine must still work after failures.
    mark = rec.mark()
    engine.open_media(str(MEDIA_DIR / "h264_1080p30_aac.mp4"))
    results["recovers_after_errors"] = rec.wait_for(mark, is_state(S.PLAYING), OPEN_TIMEOUT) is not None
    out["results"] = results
    out["ok"] = True
    engine.close()
    window.close()
    return out


def scenario_cycles(engine_name: str, cycles: int) -> dict[str, Any]:
    app, window, engine, rec, out = setup(engine_name)
    proc = psutil.Process()
    media = str(MEDIA_DIR / "h264_1080p30_aac.mp4")
    rss, threads, failures = [], [], 0
    for _ in range(cycles):
        mark = rec.mark()
        engine.open_media(media)
        if rec.wait_for(mark, is_state(S.PLAYING), OPEN_TIMEOUT) is None:
            failures += 1
        rec.pump(0.4)
        engine.stop()
        rec.pump(0.1)
        rss.append(proc.memory_info().rss / 2**20)
        threads.append(proc.num_threads())
    engine.close()
    out["open_stop_cycles"] = {
        "cycles": cycles,
        "failures": failures,
        "rss_mb_first": rss[0],
        "rss_mb_last": rss[-1],
        "threads_first": threads[0],
        "threads_last": threads[-1],
    }

    # Whole-engine create/close cycles.
    factory = default_factory()
    rss2, threads2 = [], []
    for _ in range(max(3, cycles // 3)):
        eng = factory.create(engine_name)
        eng.set_video_output(int(window.winId()))
        r = Recorder(app)
        eng.subscribe(r)
        eng.open_media(media)
        r.wait_for(0, is_state(S.PLAYING), OPEN_TIMEOUT)
        r.pump(0.3)
        eng.close()
        r.pump(0.2)
        rss2.append(proc.memory_info().rss / 2**20)
        threads2.append(proc.num_threads())
    out["engine_create_close_cycles"] = {
        "cycles": len(rss2),
        "rss_mb_first": rss2[0],
        "rss_mb_last": rss2[-1],
        "threads_first": threads2[0],
        "threads_last": threads2[-1],
    }
    out["ok"] = failures == 0
    window.close()
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--engine", required=True)
    p.add_argument("--scenario", required=True, choices=["perf", "tracks", "errors", "cycles"])
    p.add_argument("--media", default="h264_1080p30_aac.mp4")
    p.add_argument("--steady", type=float, default=8.0)
    p.add_argument("--cycles", type=int, default=15)
    a = p.parse_args()

    started = time.perf_counter()
    try:
        if a.scenario == "perf":
            result = scenario_perf(a.engine, a.media, a.steady)
        elif a.scenario == "tracks":
            result = scenario_tracks(a.engine, "multitrack_720p.mkv")
        elif a.scenario == "errors":
            result = scenario_errors(a.engine)
        else:
            result = scenario_cycles(a.engine, a.cycles)
    except Exception as exc:
        result = {"ok": False, "failure": f"{type(exc).__name__}: {exc}"}
    result.update(
        engine=a.engine,
        scenario=a.scenario,
        media=a.media if a.scenario == "perf" else None,
        wall_s=time.perf_counter() - started,
    )
    print("RESULT " + json.dumps(result, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
