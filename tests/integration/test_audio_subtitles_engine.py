"""M5 real-engine tests: track selection, external subtitles, delays and style restarts.

Uses the ``s_*`` fixtures from tools/engine-benchmark/make_media.py. Pixel-level checks that
subtitles are actually drawn live in tools/subtitle_render_check.py.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import Notice, PlaybackEvent
from babarify_frame.core.models import EngineOptions, SubtitleStyle, TrackKind
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.integration, pytest.mark.ui]

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated"
TRACKS = MEDIA / "s_black_tracks_720p.mkv"
BLACK = MEDIA / "s_black_720p.mp4"
SIDECAR = MEDIA / "s_sidecar_720p.mp4"
TIMEOUT_MS = 15_000


def _engine_params() -> list[Any]:
    # Probing mpv starts and ends a live mpv handle, which can crash this process (S1, R33),
    # so mpv is probed only when its tests are switched on.
    factory = default_factory()
    params = []
    for name in ("libvlc", "mpv"):
        if name == "mpv" and os.environ.get("BABARIFY_TEST_MPV") != "1":
            skip = pytest.mark.skip(
                reason="mpv is the alternate engine; set BABARIFY_TEST_MPV=1 (see M1 finding S1)"
            )
            params.append(pytest.param(name, marks=[skip], id=name))
            continue
        probe = factory.probe(name)
        marks = [pytest.mark.skipif(not probe.available, reason=f"{name} unavailable: {probe.detail}")]
        params.append(pytest.param(name, marks=marks, id=name))
    return params


@pytest.fixture(params=_engine_params())
def engine_name(request: pytest.FixtureRequest) -> str:
    if not TRACKS.exists():
        pytest.skip("subtitle fixtures missing: run tools/engine-benchmark/make_media.py")
    return str(request.param)


@pytest.fixture
def make_engine(engine_name: str, qtbot: QtBot) -> Iterator[Callable[[EngineOptions | None], PlaybackEngine]]:
    # Host windows are not registered with qtbot: close the engine before its window (deadlock S2).
    made: list[tuple[PlaybackEngine, QWidget]] = []

    def make(options: EngineOptions | None = None) -> PlaybackEngine:
        window = QWidget()
        window.resize(640, 360)
        window.show()
        eng = default_factory().create(engine_name, options)
        eng.set_video_output(int(window.winId()))
        made.append((eng, window))
        return eng

    yield make
    for eng, window in made:
        eng.close()
        window.close()
        window.deleteLater()


@pytest.fixture
def engine(make_engine: Callable[[EngineOptions | None], PlaybackEngine]) -> PlaybackEngine:
    return make_engine(None)


def wait_true(qtbot: QtBot, check: Callable[[], bool], timeout: int = TIMEOUT_MS) -> None:
    qtbot.waitUntil(check, timeout=timeout)


def play(qtbot: QtBot, engine: PlaybackEngine, media: Path) -> None:
    engine.open_media(str(media))
    wait_true(qtbot, lambda: engine.get_playback_state().state is S.PLAYING)
    wait_true(qtbot, lambda: engine.get_playback_state().position_ms > 300)

    def tracks_known() -> bool:
        info = engine.get_media_info()
        return info is not None and bool(info.tracks_of(TrackKind.VIDEO) or info.tracks_of(TrackKind.AUDIO))

    wait_true(qtbot, tracks_known)


def tracks(engine: PlaybackEngine, kind: TrackKind) -> list[Any]:
    info = engine.get_media_info()
    return list(info.tracks_of(kind)) if info else []


def selected(engine: PlaybackEngine, kind: TrackKind) -> list[int]:
    return [t.id for t in tracks(engine, kind) if t.selected]


def test_tracks_are_listed_with_languages(engine: PlaybackEngine, qtbot: QtBot) -> None:
    play(qtbot, engine, TRACKS)
    audio = tracks(engine, TrackKind.AUDIO)
    subs = tracks(engine, TrackKind.SUBTITLE)
    assert len(audio) == 2 and len(subs) == 2
    assert {t.language for t in audio} == {"eng", "fra"}
    assert {t.language for t in subs} == {"eng", "fra"}


def test_audio_track_switch(engine: PlaybackEngine, qtbot: QtBot) -> None:
    play(qtbot, engine, TRACKS)
    target = next(t.id for t in tracks(engine, TrackKind.AUDIO) if t.language == "fra")
    engine.select_audio_track(target)
    wait_true(qtbot, lambda: selected(engine, TrackKind.AUDIO) == [target])
    wait_true(qtbot, lambda: engine.get_playback_state().state is S.PLAYING)  # a re-seek may buffer briefly


def test_subtitle_track_select_and_off(engine: PlaybackEngine, qtbot: QtBot) -> None:
    play(qtbot, engine, TRACKS)
    target = next(t.id for t in tracks(engine, TrackKind.SUBTITLE) if t.language == "fra")
    engine.select_subtitle_track(target)
    wait_true(qtbot, lambda: selected(engine, TrackKind.SUBTITLE) == [target])
    engine.select_subtitle_track(None)
    wait_true(qtbot, lambda: selected(engine, TrackKind.SUBTITLE) == [])
    wait_true(qtbot, lambda: engine.get_playback_state().state is S.PLAYING)  # a re-seek may buffer briefly


@pytest.mark.parametrize(
    "name", ["s_ext.srt", "s_ext.vtt", "s_ext.ass", "s_ext.sub", "s_ext_cp1252.srt", "s_ext_utf8_bom.srt"]
)
def test_external_subtitle_loads_and_is_selected(engine: PlaybackEngine, qtbot: QtBot, name: str) -> None:
    play(qtbot, engine, BLACK)
    before = {t.id for t in tracks(engine, TrackKind.SUBTITLE)}
    engine.add_subtitle_file(str(MEDIA / name))

    def added_and_selected() -> bool:
        new = [t for t in tracks(engine, TrackKind.SUBTITLE) if t.id not in before]
        return bool(new) and new[0].selected

    wait_true(qtbot, added_and_selected)


@pytest.mark.parametrize("name", ["s_broken.srt", "s_empty.srt"])
def test_unreadable_subtitle_gives_notice_and_playback_continues(
    engine: PlaybackEngine, qtbot: QtBot, name: str
) -> None:
    notices: list[PlaybackEvent] = []
    engine.subscribe(lambda ev: notices.append(ev) if isinstance(ev, Notice) else None)
    play(qtbot, engine, BLACK)
    engine.add_subtitle_file(str(MEDIA / name))
    wait_true(qtbot, lambda: bool(notices), timeout=6_000)
    assert isinstance(notices[0], Notice) and notices[0].code is ErrorCode.MEDIA_OPEN_FAILED
    wait_true(qtbot, lambda: engine.get_playback_state().state is S.PLAYING)  # a re-seek may buffer briefly


def test_unknown_extension_is_rejected(engine: PlaybackEngine, qtbot: QtBot) -> None:
    play(qtbot, engine, BLACK)
    with pytest.raises(PlaybackError) as exc:
        engine.add_subtitle_file(str(MEDIA / "s_ext_unknown_ext.xyz"))
    assert exc.value.code is ErrorCode.UNSUPPORTED


def test_delays_are_applied_and_reset(engine: PlaybackEngine, qtbot: QtBot) -> None:
    play(qtbot, engine, TRACKS)
    engine.set_subtitle_delay(-750)
    engine.set_audio_delay(300)
    status = engine.get_playback_state()
    assert (status.subtitle_delay_ms, status.audio_delay_ms) == (-750, 300)
    assert status.state in (S.PLAYING, S.BUFFERING)
    engine.set_subtitle_delay(0)
    engine.set_audio_delay(0)
    play(qtbot, engine, BLACK)
    status = engine.get_playback_state()
    assert (status.subtitle_delay_ms, status.audio_delay_ms) == (0, 0)


def test_sidecar_subtitle_is_detected(engine: PlaybackEngine, qtbot: QtBot) -> None:
    play(qtbot, engine, SIDECAR)
    wait_true(qtbot, lambda: bool(tracks(engine, TrackKind.SUBTITLE)), timeout=5_000)


def test_style_options_create_a_working_engine(
    make_engine: Callable[[EngineOptions | None], PlaybackEngine], qtbot: QtBot
) -> None:
    style = SubtitleStyle(font_family="Arial", size_pct=150, text_color="#FFFF00", background_opacity=60)
    eng = make_engine(EngineOptions(subtitle_style=style))
    play(qtbot, eng, TRACKS)
    caps = eng.get_capabilities()
    assert caps.subtitle_style in ("live", "restart")
    if caps.subtitle_style == "live":
        eng.set_subtitle_style(SubtitleStyle(size_pct=80))
    else:
        with pytest.raises(PlaybackError) as exc:
            eng.set_subtitle_style(SubtitleStyle(size_pct=80))
        assert exc.value.code is ErrorCode.UNSUPPORTED
