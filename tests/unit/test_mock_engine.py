from pathlib import Path

import pytest

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import (
    EndReached,
    ErrorOccurred,
    MediaInfoChanged,
    PlaybackEvent,
    StateChanged,
)
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.core.models import TrackKind
from babarify_frame.playback.adapters.mock import MockEngine


def states(events: list[PlaybackEvent]) -> list[S]:
    return [e.new for e in events if isinstance(e, StateChanged)]


def test_initialize_moves_to_ready() -> None:
    eng = MockEngine()
    assert eng.state is S.UNINITIALIZED
    eng.initialize()
    assert eng.state is S.READY
    with pytest.raises(PlaybackError) as exc:
        eng.initialize()
    assert exc.value.code is ErrorCode.INVALID_STATE
    eng.close()


def test_commands_before_initialize_are_rejected() -> None:
    eng = MockEngine()
    with pytest.raises(PlaybackError) as exc:
        eng.open_media("mock://clip")
    assert exc.value.code is ErrorCode.INVALID_STATE


def test_open_with_autoplay_plays(engine: MockEngine, events: list[PlaybackEvent]) -> None:
    engine.open_media("mock://clip?duration=5000")
    assert states(events) == [S.LOADING, S.PLAYING]
    assert any(isinstance(e, MediaInfoChanged) for e in events)
    status = engine.get_playback_state()
    assert status.duration_ms == 5000
    assert status.uri == "mock://clip?duration=5000"


def test_open_without_autoplay_pauses(engine: MockEngine, events: list[PlaybackEvent]) -> None:
    engine.open_media("mock://clip", autoplay=False)
    assert states(events) == [S.LOADING, S.PAUSED]


def test_play_during_loading_switches_to_autoplay() -> None:
    eng = MockEngine(auto_complete_loading=False)
    eng.initialize()
    eng.open_media("mock://clip", autoplay=False)
    assert eng.state is S.LOADING
    eng.play()
    eng.complete_loading()
    assert eng.state is S.PLAYING
    eng.close()


def test_pause_play_toggle(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    engine.pause()
    assert engine.state is S.PAUSED
    engine.play()
    assert engine.state is S.PLAYING


def test_play_without_media_is_rejected(engine: MockEngine) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.play()
    assert exc.value.code is ErrorCode.INVALID_STATE


def test_seek_validation(engine: MockEngine) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.seek(1000)  # nothing loaded
    assert exc.value.code is ErrorCode.INVALID_STATE

    engine.open_media("mock://clip?duration=10000")
    engine.seek(4000)
    assert engine.get_playback_state().position_ms == 4000
    for bad in (-1, 10_001, 1.5, True, "100"):
        with pytest.raises(PlaybackError) as exc:
            engine.seek(bad)  # type: ignore[arg-type]
        assert exc.value.code is ErrorCode.INVALID_ARGUMENT, bad


def test_volume_validation(engine: MockEngine) -> None:
    engine.set_volume(0)
    engine.set_volume(150)  # mock max_volume
    assert engine.get_playback_state().volume == 150
    for bad in (-1, 151, 50.0, True):
        with pytest.raises(PlaybackError) as exc:
            engine.set_volume(bad)  # type: ignore[arg-type]
        assert exc.value.code is ErrorCode.INVALID_ARGUMENT
    assert engine.get_playback_state().volume == 150


def test_mute(engine: MockEngine) -> None:
    engine.set_muted(True)
    assert engine.get_playback_state().muted is True
    engine.set_muted(False)
    assert engine.get_playback_state().muted is False


@pytest.mark.parametrize("rate", [0.25, 1, 1.5, 4.0])
def test_rate_accepts_valid_values(engine: MockEngine, rate: float) -> None:
    engine.set_playback_rate(rate)
    assert engine.get_playback_state().rate == rate


@pytest.mark.parametrize("rate", [0.0, 0.1, 4.01, float("nan"), float("inf"), True])
def test_rate_rejects_invalid_values(engine: MockEngine, rate: float) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.set_playback_rate(rate)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_advance_respects_rate_and_reaches_end(engine: MockEngine, events: list[PlaybackEvent]) -> None:
    engine.open_media("mock://clip?duration=3000")
    engine.set_playback_rate(2.0)
    engine.advance(1000)
    assert engine.get_playback_state().position_ms == 2000
    engine.advance(1000)
    assert engine.state is S.ENDED
    assert engine.get_playback_state().position_ms == 3000
    assert any(isinstance(e, EndReached) for e in events)


def test_play_after_end_restarts(engine: MockEngine) -> None:
    engine.open_media("mock://clip?duration=1000")
    engine.advance(2000)
    assert engine.state is S.ENDED
    engine.play()
    assert engine.state is S.PLAYING
    assert engine.get_playback_state().position_ms == 0


def test_seek_after_end_pauses(engine: MockEngine) -> None:
    engine.open_media("mock://clip?duration=1000")
    engine.advance(2000)
    engine.seek(500)
    assert engine.state is S.PAUSED


def test_stop_returns_to_ready_and_play_restarts(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    engine.advance(500)
    engine.stop()
    assert engine.state is S.READY
    assert engine.get_playback_state().position_ms == 0
    engine.play()
    assert engine.state is S.PLAYING


def test_open_failure_reports_error(engine: MockEngine, events: list[PlaybackEvent]) -> None:
    engine.open_media("mock://broken?fail=open")
    assert engine.state is S.ERROR
    errors = [e.error for e in events if isinstance(e, ErrorOccurred)]
    assert errors and errors[0].code is ErrorCode.MEDIA_OPEN_FAILED
    # Recoverable: a new file can be opened.
    engine.open_media("mock://clip")
    assert engine.state is S.PLAYING


def test_missing_file_is_rejected_synchronously(engine: MockEngine, tmp_path: Path) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.open_media(str(tmp_path / "missing.mkv"))
    assert exc.value.code is ErrorCode.MEDIA_NOT_FOUND
    assert engine.state is S.READY


def test_existing_file_and_file_uri_are_accepted(engine: MockEngine, tmp_path: Path) -> None:
    media = tmp_path / "clip with space.mkv"
    media.write_bytes(b"\x00")
    engine.open_media(str(media))
    assert engine.get_playback_state().uri == str(media.resolve())
    engine.open_media(media.as_uri())
    assert engine.get_playback_state().uri == str(media.resolve())


@pytest.mark.parametrize(
    ("uri", "code"),
    [
        ("", ErrorCode.INVALID_ARGUMENT),
        ("   ", ErrorCode.INVALID_ARGUMENT),
        ("mock://a\nb", ErrorCode.INVALID_ARGUMENT),
        ("http://example.com/a.mp4", ErrorCode.UNSUPPORTED),
        ("smb://server/share/a.mkv", ErrorCode.UNSUPPORTED),
    ],
)
def test_untrusted_uris_are_rejected(engine: MockEngine, uri: str, code: ErrorCode) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.open_media(uri)
    assert exc.value.code is code


def test_media_info_tracks(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    info = engine.get_media_info()
    assert info is not None
    assert len(info.tracks_of(TrackKind.AUDIO)) == 1
    assert len(info.tracks_of(TrackKind.SUBTITLE)) == 1


def test_capabilities(engine: MockEngine) -> None:
    caps = engine.get_capabilities()
    assert caps.engine_name == "mock"
    assert caps.hardware_decoding == "unavailable"


def test_buffering_round_trip(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    engine.simulate_buffering(True)
    assert engine.state is S.BUFFERING
    engine.simulate_buffering(False)
    assert engine.state is S.PLAYING


def test_invalid_engine_transition_is_rejected_and_recorded(engine: MockEngine) -> None:
    # READY -> PLAYING skips loading and must be refused.
    engine.simulate_buffering(False)
    assert engine.state is S.READY
    assert engine.rejected_transitions == [(S.READY, S.PLAYING)]


def test_close_is_idempotent_and_releases(engine: MockEngine, events: list[PlaybackEvent]) -> None:
    engine.open_media("mock://clip")
    engine.close()
    engine.close()
    assert engine.state is S.CLOSED
    assert engine.closed_resources
    assert engine.calls.count("close") == 1
    assert states(events)[-1] is S.CLOSED
    with pytest.raises(PlaybackError) as exc:
        engine.play()
    assert exc.value.code is ErrorCode.INVALID_STATE


def test_close_after_error_still_cleans_up(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    engine.simulate_error()
    engine.close()
    assert engine.state is S.CLOSED
    assert engine.closed_resources


def test_unsubscribe_stops_events(engine: MockEngine) -> None:
    received: list[PlaybackEvent] = []
    unsubscribe = engine.subscribe(received.append)
    engine.open_media("mock://clip")
    count = len(received)
    unsubscribe()
    engine.pause()
    assert len(received) == count


def test_failing_listener_does_not_break_engine(engine: MockEngine) -> None:
    def boom(_: PlaybackEvent) -> None:
        raise RuntimeError("listener bug")

    engine.subscribe(boom)
    engine.open_media("mock://clip")
    assert engine.state is S.PLAYING


def test_video_output_validation(engine: MockEngine) -> None:
    engine.set_video_output(1234)
    assert engine.window_id == 1234
    engine.set_video_output(None)
    for bad in (0, -5):
        with pytest.raises(PlaybackError):
            engine.set_video_output(bad)
