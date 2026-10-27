"""Shutdown in every playback state (M4): close() must finish promptly and leave CLOSED.

A hang here would freeze the app on exit. Each case uses a fresh libVLC engine and a host
window that is closed only after the engine (see the close-before-window rule).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.integration, pytest.mark.ui]

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "generated"
H264 = MEDIA / "h264_1080p30_aac.mp4"
CLOSE_LIMIT_S = 5.0  # fixed before the first run


def _available() -> bool:
    return H264.exists() and default_factory().probe("libvlc").available


def _wait(qtbot: QtBot, check: Callable[[], bool]) -> None:
    qtbot.waitUntil(check, timeout=15_000)


def _loading(e: PlaybackEngine, q: QtBot) -> None:
    e.open_media(str(H264))  # close immediately, while still loading


def _playing(e: PlaybackEngine, q: QtBot) -> None:
    e.open_media(str(H264))
    _wait(q, lambda: e.get_playback_state().position_ms > 500)


def _paused(e: PlaybackEngine, q: QtBot) -> None:
    _playing(e, q)
    e.pause()
    _wait(q, lambda: e.get_playback_state().state is S.PAUSED)


def _mid_seek(e: PlaybackEngine, q: QtBot) -> None:
    _playing(e, q)
    e.seek(20_000)  # close right after issuing the seek


def _ended(e: PlaybackEngine, q: QtBot) -> None:
    _playing(e, q)
    e.seek(29_500)
    _wait(q, lambda: e.get_playback_state().state is S.ENDED)


def _error(e: PlaybackEngine, q: QtBot) -> None:
    e.open_media(str(MEDIA / "not_media.mp4"))
    _wait(q, lambda: e.get_playback_state().state is S.ERROR)


def _stopped(e: PlaybackEngine, q: QtBot) -> None:
    _playing(e, q)
    e.stop()


def _seek_storm_then_close(e: PlaybackEngine, q: QtBot) -> None:
    _playing(e, q)
    for target in (5_000, 25_000, 1_000, 15_000, 10_000):
        e.seek(target)  # several in-flight seeks


CASES = {
    "loading": _loading,
    "playing": _playing,
    "paused": _paused,
    "mid_seek": _mid_seek,
    "ended": _ended,
    "error": _error,
    "stopped": _stopped,
    "after_seek_burst": _seek_storm_then_close,
}


@pytest.mark.parametrize("case", list(CASES))
def test_close_in_every_state_is_prompt(qtbot: QtBot, case: str) -> None:
    if not _available():
        pytest.skip("libVLC or generated media unavailable")
    window = QWidget()
    window.resize(640, 360)
    window.show()
    engine = default_factory().create("libvlc")
    try:
        engine.set_video_output(int(window.winId()))
        CASES[case](engine, qtbot)
    finally:
        start = time.perf_counter()
        engine.close()
        elapsed = time.perf_counter() - start
        window.close()
        window.deleteLater()
    assert engine.get_playback_state().state is S.CLOSED
    assert elapsed < CLOSE_LIMIT_S, f"close() took {elapsed:.2f}s in state '{case}'"


@pytest.mark.parametrize("delay_ms", [150, 600])
def test_app_exits_cleanly_when_closed_while_opening(tmp_path: Path, delay_ms: int) -> None:
    if not _available():
        pytest.skip("libVLC or generated media unavailable")
    env = {**os.environ, "BABARIFY_CONFIG_DIR": str(tmp_path)}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "babarify_frame",
            str(MEDIA / "hevc_2160p30_aac.mkv"),
            "--smoke-test",
            str(delay_ms),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
