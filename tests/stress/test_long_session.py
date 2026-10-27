"""Long-session and seek-storm reliability (M4). Run explicitly: ``pytest -m stress -s``.

Thresholds were fixed before the first run (see docs/milestones/M4/acceptance-report.md).
``BABARIFY_LONG_SESSION_MIN`` overrides the session length (default 10 minutes).
"""

from __future__ import annotations

import json
import os
import random
import statistics
import time
from pathlib import Path

import psutil
import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from babarify_frame.core.events import ErrorOccurred, PlaybackEvent
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.stress, pytest.mark.integration, pytest.mark.ui]

MEDIA = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "media" / "generated"
SESSION_MIN = float(os.environ.get("BABARIFY_LONG_SESSION_MIN", "10"))
WARMUP_S = 120
MAX_RSS_GROWTH_MB = 64
MAX_HANDLE_GROWTH = 300
MAX_THREAD_GROWTH = 4
MAX_DRIFT = 0.02  # playback position vs wall clock
SEEKS = 300
SEEK_TIMEOUT_S = 5.0
SEEK_FILES = [
    ("hevc_2160p30_aac.mkv", 20_000),
    ("e_mkv_no_cues.mkv", 10_000),
    ("e_fragmented.mp4", 8_000),
    ("e_long_1h_240p.mkv", 3_600_000),
    ("h264_1080p30_aac.mp4", 30_000),
]


def _sample() -> dict[str, float]:
    p = psutil.Process()
    return {
        "rss_mb": round(p.memory_info().rss / 2**20, 1),
        "threads": p.num_threads(),
        "handles": p.num_handles(),
    }


def _pump(qtbot: QtBot, seconds: float) -> None:
    qtbot.wait(int(seconds * 1000))


def test_long_session_continuous_playback(qtbot: QtBot) -> None:
    media = MEDIA / "e_long_1h_240p.mkv"
    if not media.exists():
        pytest.skip("generated media missing")
    window = QWidget()
    window.resize(960, 540)
    window.show()
    engine = default_factory().create("libvlc")
    errors: list[PlaybackEvent] = []
    engine.subscribe(lambda ev: errors.append(ev) if isinstance(ev, ErrorOccurred) else None)
    samples = []
    try:
        engine.set_video_output(int(window.winId()))
        engine.open_media(str(media))
        qtbot.waitUntil(lambda: engine.get_playback_state().position_ms > 500, timeout=15_000)
        start_wall, start_pos = time.perf_counter(), engine.get_playback_state().position_ms
        warm: dict[str, float] = {}
        end = start_wall + SESSION_MIN * 60
        while time.perf_counter() < end:
            _pump(qtbot, 15)
            elapsed = time.perf_counter() - start_wall
            samples.append(
                {"t_s": round(elapsed), **_sample(), "pos_ms": engine.get_playback_state().position_ms}
            )
            if not warm and elapsed >= WARMUP_S:
                warm = samples[-1]
        final = _sample()
        played_ms = engine.get_playback_state().position_ms - start_pos
        wall_ms = (time.perf_counter() - start_wall) * 1000
        state = engine.get_playback_state().state
        stats = dict(engine.playback_stats())
    finally:
        engine.close()
        window.close()
        window.deleteLater()
    result = {
        "minutes": SESSION_MIN,
        "drift": round(played_ms / wall_ms - 1, 4),
        "rss_growth_mb": round(final["rss_mb"] - warm["rss_mb"], 1),
        "handle_growth": final["handles"] - warm["handles"],
        "thread_growth": final["threads"] - warm["threads"],
        "errors": len(errors),
        "final_state": state.value,
        "frames": stats,
        "samples": samples,
    }
    print("LONG_SESSION " + json.dumps(result))
    assert not errors
    assert state is S.PLAYING
    assert abs(result["drift"]) <= MAX_DRIFT  # type: ignore[arg-type]
    assert result["rss_growth_mb"] <= MAX_RSS_GROWTH_MB  # type: ignore[operator]
    assert result["handle_growth"] <= MAX_HANDLE_GROWTH  # type: ignore[operator]
    assert result["thread_growth"] <= MAX_THREAD_GROWTH  # type: ignore[operator]


def test_seek_storm(qtbot: QtBot) -> None:
    files = [(MEDIA / name, duration) for name, duration in SEEK_FILES]
    if not all(path.exists() for path, _ in files):
        pytest.skip("generated media missing")
    rng = random.Random(4)  # deterministic sequence
    window = QWidget()
    window.resize(960, 540)
    window.show()
    engine = default_factory().create("libvlc")
    errors: list[PlaybackEvent] = []
    engine.subscribe(lambda ev: errors.append(ev) if isinstance(ev, ErrorOccurred) else None)
    settle_ms: list[float] = []
    timeouts = []
    try:
        engine.set_video_output(int(window.winId()))
        per_file = SEEKS // len(files)
        for path, duration in files:
            engine.open_media(str(path))
            qtbot.waitUntil(lambda: engine.get_playback_state().state is S.PLAYING, timeout=15_000)
            for i in range(per_file):
                if i % 10 == 5:
                    engine.pause()
                elif i % 10 == 8:
                    engine.play()
                target = rng.randrange(0, max(1, duration - 2_000))
                t0 = time.perf_counter()
                engine.seek(target)
                deadline = t0 + SEEK_TIMEOUT_S
                while time.perf_counter() < deadline:
                    qtbot.wait(5)
                    st = engine.get_playback_state()
                    # Real resumption, not just an accepted target: while playing the position must
                    # move past the target; while paused it must sit at the target.
                    resumed = st.state is S.PLAYING and target + 300 <= st.position_ms <= target + 3_000
                    parked = st.state is S.PAUSED and abs(st.position_ms - target) <= 1_500
                    if resumed or parked or st.state is S.ENDED:
                        settle_ms.append((time.perf_counter() - t0) * 1000)
                        break
                else:
                    timeouts.append((path.name, target, engine.get_playback_state().position_ms))
    finally:
        engine.close()
        window.close()
        window.deleteLater()
    s = sorted(settle_ms)
    result = {
        "seeks": len(settle_ms) + len(timeouts),
        "timeouts": timeouts,
        "errors": len(errors),
        "settle_ms_p50": round(statistics.median(s), 1),
        "settle_ms_p95": round(s[int(len(s) * 0.95) - 1], 1),
        "settle_ms_max": round(s[-1], 1),
    }
    print("SEEK_STORM " + json.dumps(result))
    assert not timeouts
    assert not errors
