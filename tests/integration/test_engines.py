"""Real-engine tests. Skipped when an engine library or the generated media is missing.

libVLC (the selected engine, ADR-0001) runs by default. mpv runs only with
BABARIFY_TEST_MPV=1: processes that create several mpv instances end in an access
violation (M1 finding S1), which would fail the whole pytest process.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import ErrorOccurred, PlaybackEvent, StateChanged
from babarify_frame.core.models import EngineOptions, TrackKind
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.integration, pytest.mark.ui]

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated"
MANIFEST = ROOT / "tools" / "engine-benchmark" / "media-manifest.json"
H264 = MEDIA / "h264_1080p30_aac.mp4"
TIMEOUT_MS = 15_000


def _engine_params() -> list[Any]:
    factory = default_factory()
    params = []
    for name in ("libvlc", "mpv"):
        probe = factory.probe(name)
        marks = [pytest.mark.skipif(not probe.available, reason=f"{name} unavailable: {probe.detail}")]
        if name == "mpv":
            marks.append(
                pytest.mark.skipif(
                    os.environ.get("BABARIFY_TEST_MPV") != "1",
                    reason="mpv is the alternate engine; set BABARIFY_TEST_MPV=1 (see M1 finding S1)",
                )
            )
        params.append(pytest.param(name, marks=marks, id=name))
    return params


def _valid_media() -> list[Any]:
    if not MANIFEST.exists():
        return []
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    return [pytest.param(e, id=e["file"]) for e in entries if e["kind"] == "valid"]


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


def record_states(engine: PlaybackEngine) -> list[S]:
    states: list[S] = []
    engine.subscribe(lambda ev: states.append(ev.new) if isinstance(ev, StateChanged) else None)
    return states


@pytest.mark.parametrize("media", _valid_media())
def test_corpus_file_plays_with_correct_media_info(
    engine: PlaybackEngine, qtbot: QtBot, media: dict[str, Any]
) -> None:
    expect = media["expect"]
    engine.open_media(str(MEDIA / media["file"]))
    wait_state(qtbot, engine, S.PLAYING)
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 300)

    def info_complete() -> bool:
        info = engine.get_media_info()
        return info is not None and ("width" not in expect or info.width is not None)

    wait_true(qtbot, info_complete)
    info = engine.get_media_info()
    assert info is not None
    if "video" in expect:
        assert info.video_codec == expect["video"]
        assert (info.width, info.height) == (expect["width"], expect["height"])
    else:
        assert info.video_codec is None
    if "audio" in expect:
        assert info.audio_codec == expect["audio"]
    if "audio_tracks" in expect:
        assert len(info.tracks_of(TrackKind.AUDIO)) == expect["audio_tracks"]
        assert len(info.tracks_of(TrackKind.SUBTITLE)) == expect["subtitle_tracks"]
    assert info.duration_ms is not None and info.duration_ms > 0


def test_controls_play_pause_seek_volume_rate(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)
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
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 15_500)


def test_open_paused(engine: PlaybackEngine, qtbot: QtBot) -> None:
    states = record_states(engine)
    engine.open_media(str(H264), autoplay=False)
    wait_state(qtbot, engine, S.PAUSED)
    assert S.PLAYING not in states


def test_stop_then_play_restarts(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(H264))
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 1_000)
    engine.stop()
    assert engine.get_playback_state().state is S.READY
    assert engine.get_playback_state().position_ms == 0
    engine.play()
    wait_state(qtbot, engine, S.PLAYING)
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 300)


def test_end_then_play_restarts(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)
    engine.seek(29_000)
    wait_state(qtbot, engine, S.ENDED)
    engine.play()
    wait_state(qtbot, engine, S.PLAYING)
    wait_true(qtbot, lambda: 0 < engine.get_playback_state().position_ms < 10_000)


def test_seek_after_end_pauses_at_target(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)
    engine.seek(29_000)
    wait_state(qtbot, engine, S.ENDED)
    engine.seek(10_000)
    wait_state(qtbot, engine, S.PAUSED)
    wait_true(qtbot, lambda: abs(engine.get_playback_state().position_ms - 10_000) < 1_500)


@pytest.mark.parametrize("bad", ["not_media.mp4", "truncated.mp4"])
def test_invalid_media_fails_without_playing_and_engine_recovers(
    engine: PlaybackEngine, qtbot: QtBot, bad: str
) -> None:
    states = record_states(engine)
    errors: list[PlaybackEvent] = []
    engine.subscribe(lambda ev: errors.append(ev) if isinstance(ev, ErrorOccurred) else None)
    engine.open_media(str(MEDIA / bad))
    wait_state(qtbot, engine, S.ERROR)
    assert errors, "an ErrorOccurred event must accompany the ERROR state"
    assert isinstance(errors[0], ErrorOccurred)
    assert errors[0].error.code is ErrorCode.MEDIA_OPEN_FAILED
    assert errors[0].error.detail[:2] not in ("3 ", "4 "), "engine log level leaked into the message (R14)"
    assert S.PLAYING not in states, f"bad media must not appear to play: {states}"

    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)


def test_missing_file_rejected_before_engine(engine: PlaybackEngine) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.open_media(str(MEDIA / "does-not-exist.mkv"))
    assert exc.value.code is ErrorCode.MEDIA_NOT_FOUND


def test_tracks_are_listed(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(MEDIA / "multitrack_720p.mkv"))
    wait_state(qtbot, engine, S.PLAYING)
    wait_true(qtbot, lambda: engine.get_media_info() is not None)
    info = engine.get_media_info()
    assert info is not None
    assert len(info.tracks_of(TrackKind.AUDIO)) == 2
    assert len(info.tracks_of(TrackKind.SUBTITLE)) == 2


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


# --------------------------------------------------------------------- M4
def _edge_media(kind: str) -> list[Any]:
    if not MANIFEST.exists():
        return []
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    return [pytest.param(e, id=e["file"]) for e in entries if e.get("set") == "edge" and e["kind"] == kind]


@pytest.mark.parametrize("name", _engine_params())
def test_hardware_decoding_off_reports_software(qtbot: QtBot, name: str) -> None:
    """M4 regression: libVLC ignored --avcodec-hw at instance level and kept using the GPU."""
    if not H264.exists():
        pytest.skip("generated media missing")
    window = QWidget()
    window.show()
    eng = default_factory().create(name, EngineOptions(hardware_decoding=False))
    try:
        assert eng.get_capabilities().hardware_decoding == "disabled"
        eng.set_video_output(int(window.winId()))
        eng.open_media(str(H264))
        qtbot.waitUntil(lambda: eng.get_playback_state().position_ms > 800, timeout=TIMEOUT_MS)
        assert eng.diagnostics()["decoder"] == "software"
    finally:
        eng.close()
        window.close()
        window.deleteLater()


def test_decoder_is_reported_once_decoding(engine: PlaybackEngine, qtbot: QtBot) -> None:
    engine.open_media(str(H264))
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 800)
    decoder = engine.diagnostics()["decoder"]
    assert decoder == "software" or decoder.startswith("hardware ("), decoder


@pytest.mark.parametrize("media", _edge_media("damaged"))
def test_damaged_media_never_hangs_and_engine_recovers(
    engine: PlaybackEngine, qtbot: QtBot, media: dict[str, Any]
) -> None:
    engine.open_media(str(MEDIA / media["file"]))
    # Either plays through (decoder conceals the damage) or fails cleanly; it must not hang.
    wait_state(qtbot, engine, S.ENDED, S.ERROR)
    engine.open_media(str(H264))
    wait_state(qtbot, engine, S.PLAYING)


@pytest.mark.parametrize("media", _edge_media("invalid"))
def test_invalid_edge_media_fails_cleanly(
    engine: PlaybackEngine, qtbot: QtBot, media: dict[str, Any]
) -> None:
    engine.open_media(str(MEDIA / media["file"]))
    wait_state(qtbot, engine, S.ERROR)


def test_seek_near_end_of_one_hour_file(engine: PlaybackEngine, qtbot: QtBot) -> None:
    long_file = MEDIA / "e_long_1h_240p.mkv"
    if not long_file.exists():
        pytest.skip("generated media missing")
    engine.open_media(str(long_file))
    wait_state(qtbot, engine, S.PLAYING)
    wait_true(qtbot, lambda: (engine.get_playback_state().duration_ms or 0) > 3_590_000)
    engine.seek(3_540_000)
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms >= 3_540_000)


def test_seek_immediately_after_pause_reports_target(engine: PlaybackEngine, qtbot: QtBot) -> None:
    """M4 regression (seek storm): a seek issued before the pause took effect was not reported."""
    engine.open_media(str(H264))
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 1_000)
    engine.pause()
    engine.seek(18_000)  # no wait: the pause has not taken effect yet
    wait_state(qtbot, engine, S.PAUSED)
    qtbot.wait(500)
    assert abs(engine.get_playback_state().position_ms - 18_000) < 1_500
    engine.play()
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 18_300)
