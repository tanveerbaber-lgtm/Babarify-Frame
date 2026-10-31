"""M5 contract behaviour (tracks, external subtitles, delays, style) on the mock engine."""

from pathlib import Path

import pytest

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import Notice, PlaybackEvent
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.core.models import SubtitlePosition, SubtitleStyle, TrackKind
from babarify_frame.playback.adapters.mock import MockEngine


def selected(engine: MockEngine, kind: TrackKind) -> list[int]:
    info = engine.get_media_info()
    assert info is not None
    return [t.id for t in info.tracks_of(kind) if t.selected]


def test_select_audio_track(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    assert selected(engine, TrackKind.AUDIO) == [2]
    engine.select_audio_track(3)
    assert selected(engine, TrackKind.AUDIO) == [3]


def test_select_subtitle_and_off(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    assert selected(engine, TrackKind.SUBTITLE) == []
    engine.select_subtitle_track(5)
    assert selected(engine, TrackKind.SUBTITLE) == [5]
    engine.select_subtitle_track(None)
    assert selected(engine, TrackKind.SUBTITLE) == []


@pytest.mark.parametrize("bad", [99, 1, 4])  # unknown id, the video track, a subtitle id for audio
def test_invalid_audio_track_is_rejected(engine: MockEngine, bad: int) -> None:
    engine.open_media("mock://clip")
    with pytest.raises(PlaybackError) as exc:
        engine.select_audio_track(bad)
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_track_selection_needs_media(engine: MockEngine) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.select_subtitle_track(None)
    assert exc.value.code is ErrorCode.INVALID_STATE


def test_add_subtitle_file(engine: MockEngine, tmp_path: Path) -> None:
    sub = tmp_path / "movie.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    engine.open_media("mock://clip")
    engine.add_subtitle_file(str(sub))
    info = engine.get_media_info()
    assert info is not None
    added = [t for t in info.tracks_of(TrackKind.SUBTITLE) if t.title == "movie.srt"]
    assert added and added[0].selected


def test_unreadable_subtitle_gives_notice_not_error(
    engine: MockEngine, events: list[PlaybackEvent], tmp_path: Path
) -> None:
    sub = tmp_path / "broken.srt"
    sub.write_bytes(b"\x00\x01")
    engine.open_media("mock://clip")
    engine.add_subtitle_file(str(sub))
    notices = [e for e in events if isinstance(e, Notice)]
    assert notices and notices[0].code is ErrorCode.MEDIA_OPEN_FAILED
    assert engine.state is S.PLAYING  # playback continues


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("missing.srt", None, ErrorCode.MEDIA_NOT_FOUND),
        ("subs.xyz", b"1\n", ErrorCode.UNSUPPORTED),
        ("noext", b"1\n", ErrorCode.UNSUPPORTED),
    ],
)
def test_add_subtitle_validation(
    engine: MockEngine, tmp_path: Path, name: str, content: bytes | None, code: ErrorCode
) -> None:
    path = tmp_path / name
    if content is not None:
        path.write_bytes(content)
    engine.open_media("mock://clip")
    with pytest.raises(PlaybackError) as exc:
        engine.add_subtitle_file(str(path))
    assert exc.value.code is code


def test_oversized_subtitle_is_rejected(
    engine: MockEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from babarify_frame.playback import contracts

    monkeypatch.setattr(contracts, "MAX_SUBTITLE_BYTES", 10)
    path = tmp_path / "big.srt"
    path.write_bytes(b"x" * 11)
    engine.open_media("mock://clip")
    with pytest.raises(PlaybackError) as exc:
        engine.add_subtitle_file(str(path))
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_control_characters_in_subtitle_path_are_rejected(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    with pytest.raises(PlaybackError) as exc:
        engine.add_subtitle_file("C:/subs\n.srt")
    assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_delays_are_validated_and_reported(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    engine.set_subtitle_delay(-1500)
    engine.set_audio_delay(250)
    status = engine.get_playback_state()
    assert (status.subtitle_delay_ms, status.audio_delay_ms) == (-1500, 250)
    for bad in (60_001, -60_001, 1.5, True):
        with pytest.raises(PlaybackError) as exc:
            engine.set_subtitle_delay(bad)  # type: ignore[arg-type]
        assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_delays_reset_for_a_new_file(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    engine.set_subtitle_delay(700)
    engine.open_media("mock://other")
    assert engine.get_playback_state().subtitle_delay_ms == 0


def test_live_subtitle_style(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    engine.set_subtitle_style(SubtitleStyle(text_color="#ffff00", size_pct=150))
    assert engine.subtitle_style.text_color == "#FFFF00"
    assert engine.subtitle_style.size_pct == 150


@pytest.mark.parametrize(
    ("raw", "field", "expected"),
    [
        ({"size_pct": 500}, "size_pct", 200),
        ({"size_pct": 5}, "size_pct", 50),
        ({"size_pct": "big"}, "size_pct", 100),
        ({"text_color": "red"}, "text_color", "#FFFFFF"),
        ({"text_color": "#00ff00"}, "text_color", "#00FF00"),
        ({"background_opacity": 150}, "background_opacity", 100),
        ({"position": "sideways"}, "position", SubtitlePosition.BOTTOM),
        ({"position": "high"}, "position", SubtitlePosition.HIGH),
        ({"font_family": 42}, "font_family", ""),
    ],
)
def test_subtitle_style_from_untrusted_data(raw: dict[str, object], field: str, expected: object) -> None:
    assert getattr(SubtitleStyle.from_dict(raw), field) == expected


def test_subtitle_style_round_trip() -> None:
    style = SubtitleStyle("Segoe UI", 125, "#FFFF00", 60, SubtitlePosition.RAISED)
    assert SubtitleStyle.from_dict(style.to_dict()) == style
