"""Resource stability under repeated use (M2). Run explicitly: ``pytest -m stress -s``.

Thresholds were fixed BEFORE the first run (see docs/milestones/M2/acceptance-report.md):
measurements start after a warm-up so one-time caches (D3D11 device, decoder pools,
allocator arenas) are excluded. 64 MB is roughly twice the cycle-to-cycle variation seen
in M1; a leak of >= 1.3 MB per cycle would exceed it within 50 cycles.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psutil
import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.stress, pytest.mark.integration, pytest.mark.ui]

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated"
MANIFEST = ROOT / "tools" / "engine-benchmark" / "media-manifest.json"

OPEN_CYCLES = 60
ENGINE_CYCLES = int(os.environ.get("BABARIFY_ENGINE_CYCLES", "15"))
WARMUP = 10
ENGINE_WARMUP = 3
MAX_RSS_GROWTH_MB = 64
MAX_THREAD_GROWTH = 4
MAX_HANDLE_GROWTH = 300


def _sample() -> dict[str, float]:
    proc = psutil.Process()
    return {
        "rss_mb": proc.memory_info().rss / 2**20,
        "threads": proc.num_threads(),
        "handles": proc.num_handles(),
    }


def _media_files() -> list[Path]:
    if not MANIFEST.exists():
        pytest.skip("generated media missing: run tools/engine-benchmark/make_media.py")
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    return [MEDIA / e["file"] for e in entries if e["kind"] == "valid"]


def _check(name: str, warm: dict[str, float], end: dict[str, float]) -> dict[str, object]:
    result = {
        "name": name,
        "warm": warm,
        "end": end,
        "rss_growth_mb": round(end["rss_mb"] - warm["rss_mb"], 1),
        "thread_growth": end["threads"] - warm["threads"],
        "handle_growth": end["handles"] - warm["handles"],
    }
    print("STRESS " + json.dumps(result))
    return result


def test_repeated_open_on_one_engine(qtbot: QtBot) -> None:
    files = _media_files()
    window = QWidget()  # not registered with qtbot: the engine must close before the window
    window.resize(640, 360)
    window.show()
    engine = default_factory().create("libvlc")
    failures = []
    try:
        engine.set_video_output(int(window.winId()))
        warm: dict[str, float] = {}
        for i in range(OPEN_CYCLES):
            path = files[i % len(files)]
            engine.open_media(str(path))
            try:
                qtbot.waitUntil(lambda: engine.get_playback_state().position_ms > 200, timeout=15_000)
            except Exception:
                failures.append(path.name)
            if i % 3 == 1 and engine.get_playback_state().state in (S.PLAYING, S.PAUSED):
                engine.seek(1_000)
            if i % 3 == 2:
                engine.stop()
            if i + 1 == WARMUP:
                warm = _sample()
        end = _sample()
    finally:
        engine.close()
        window.close()
        window.deleteLater()
    result = _check("open_cycles", warm, end)
    assert not failures, f"files that did not start playing: {failures}"
    assert result["rss_growth_mb"] <= MAX_RSS_GROWTH_MB  # type: ignore[operator]
    assert result["thread_growth"] <= MAX_THREAD_GROWTH  # type: ignore[operator]
    assert result["handle_growth"] <= MAX_HANDLE_GROWTH  # type: ignore[operator]


def test_repeated_engine_create_close(qtbot: QtBot) -> None:
    media = _media_files()[0]
    factory = default_factory()
    window = QWidget()
    window.resize(640, 360)
    window.show()
    warm: dict[str, float] = {}
    try:
        for i in range(ENGINE_CYCLES):
            engine = factory.create("libvlc")
            try:
                engine.set_video_output(int(window.winId()))
                engine.open_media(str(media))
                qtbot.waitUntil(lambda e=engine: e.get_playback_state().position_ms > 200, timeout=15_000)
            finally:
                engine.close()
            time.sleep(0.1)
            if i + 1 == ENGINE_WARMUP:
                warm = _sample()
        end = _sample()
    finally:
        window.close()
        window.deleteLater()
    result = _check("engine_cycles", warm, end)
    assert result["rss_growth_mb"] <= MAX_RSS_GROWTH_MB  # type: ignore[operator]
    assert result["thread_growth"] <= MAX_THREAD_GROWTH  # type: ignore[operator]
    assert result["handle_growth"] <= MAX_HANDLE_GROWTH  # type: ignore[operator]
