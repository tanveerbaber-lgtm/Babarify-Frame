"""Real-engine smoke tests. Skipped when an engine library or the generated media is missing."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import ErrorOccurred, PlaybackEvent
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.core.models import TrackKind
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.integration, pytest.mark.ui]

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "generated"
H264 = MEDIA / "h264_1080p30_aac.mp4"
TIMEOUT_MS = 15_000


def _engine_params() -> list[object]:
    factory = default_factory()
    params = []
    for name in ("libvlc", "mpv"):
        probe = factory.probe(name)
        params.append(
            pytest.param(
                name,
                marks=pytest.mark.skipif(not probe.available, reason=f"{name} unavailable: {probe.detail}"),
            )
        )
    return params


@pytest.fixture(params=_engine_params())
def engine(request: pytest.FixtureRequest, qtbot: QtBot) -> Iterator[PlaybackEngine]:
    if not H264.exists():
        pytest.skip("generated media missing: run tools/engine-benchmark/make_media.py")
    # The window is deliberately NOT registered with qtbot: pytest-qt would destroy it before
    # this fixture's teardown, i.e. while the engine still renders into it. Destroying a
    # host window under a live libVLC video output deadlocks (GUI thread holds the GIL while
    # DestroyWindow waits on libVLC's window thread, which waits on the GIL in a callback).
    # Rule: always close the engine before its host window.
    window = QWidget()
    window.resize(640, 360)
    window.show()
    eng = default_factory().create(request.param)
    eng.set_video_output(int(window.winId()))
    yield eng
    eng.close()
    assert eng.get_playback_state().state is S.CLOSED
    window.close()
    window.deleteLater()


def wait_state(qtbot: QtBot, engine: PlaybackEngine, *states: S) -> None:
    qtbot.waitUntil(lambda: engine.get_playback_state().state in states, timeout=TIMEOUT_MS)


def wait_true(qtbot: QtBot, check: Callable[[], bool]) -> None:
    qtbot.waitUntil(check, timeout=TIMEOUT_MS)


def test_play_pause_seek_volume(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 300)

    wait_true(qtbot, lambda: engine.get_media_info() is not None)
    info = engine.get_media_info()
    assert info is not None
    assert (info.width, info.height) == (1920, 1080)
    assert info.video_codec == "h264"
    assert info.duration_ms is not None and 29_000 <= info.duration_ms <= 31_000

    engine.pause()
    wait_state(qtbot, engine, S.PAUSED)

    engine.seek(15_000)
    wait_true(qtbot, lambda: abs(engine.get_playback_state().position_ms - 15_000) < 1_500)

    engine.set_volume(50)
    engine.set_muted(True)
    engine.set_playback_rate(1.5)
    status = engine.get_playback_state()
    assert (status.volume, status.muted, status.rate) == (50, True, 1.5)

    engine.play()
    wait_state(qtbot, engine, S.PLAYING)
    engine.stop()
    assert engine.get_playback_state().state is S.READY


def test_tracks_are_listed(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(MEDIA / "multitrack_720p.mkv"))
    wait_state(qtbot, engine, S.PLAYING)
    wait_true(qtbot, lambda: engine.get_media_info() is not None)
    info = engine.get_media_info()
    assert info is not None
    assert len(info.tracks_of(TrackKind.AUDIO)) == 2
    assert len(info.tracks_of(TrackKind.SUBTITLE)) == 2


@pytest.mark.parametrize("bad", ["not_media.mp4", "truncated.mp4"])
def test_invalid_media_fails_gracefully_and_engine_recovers(
    engine: PlaybackEngine, qtbot: QtBot, bad: str
) -> None:
    errors: list[PlaybackEvent] = []
    engine.subscribe(lambda ev: errors.append(ev) if isinstance(ev, ErrorOccurred) else None)
    engine.open_media(str(MEDIA / bad))
    wait_state(qtbot, engine, S.ERROR)
    assert errors, "an ErrorOccurred event must accompany the ERROR state"

    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)


def test_missing_file_rejected_before_engine(engine: PlaybackEngine) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.open_media(str(MEDIA / "does-not-exist.mkv"))
    assert exc.value.code is ErrorCode.MEDIA_NOT_FOUND


def test_end_of_media_reports_ended(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)
    engine.seek(28_500)
    wait_state(qtbot, engine, S.ENDED)


@pytest.mark.parametrize("name", _engine_params())
def test_repeated_create_open_close_is_stable(qtbot: QtBot, name: str) -> None:
    if not H264.exists():
        pytest.skip("generated media missing")
    factory = default_factory()
    window = QWidget()  # not registered with qtbot: engines must close before the window (see fixture)
    window.show()
    try:
        for _ in range(3):
            eng = factory.create(name)
            try:
                eng.set_video_output(int(window.winId()))
                eng.open_media(str(H264))
                qtbot.waitUntil(lambda e=eng: e.get_playback_state().state is S.PLAYING, timeout=TIMEOUT_MS)
                time.sleep(0.2)
            finally:
                eng.close()
            assert eng.get_playback_state().state is S.CLOSED
    finally:
        window.close()
        window.deleteLater()
