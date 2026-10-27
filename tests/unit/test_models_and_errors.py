import dataclasses

import pytest

from babarify_frame.core.errors import USER_MESSAGES, ErrorCode, PlaybackError
from babarify_frame.core.models import MediaInfo, PlaybackStatus, TrackInfo, TrackKind
from babarify_frame.core.models import PlaybackState as S


def test_models_are_immutable() -> None:
    status = PlaybackStatus(state=S.READY)
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.position_ms = 5  # type: ignore[misc]


def test_tracks_of_filters_by_kind() -> None:
    info = MediaInfo(
        uri="x",
        tracks=(
            TrackInfo(1, TrackKind.VIDEO),
            TrackInfo(2, TrackKind.AUDIO),
            TrackInfo(3, TrackKind.AUDIO),
            TrackInfo(4, TrackKind.SUBTITLE),
        ),
    )
    assert [t.id for t in info.tracks_of(TrackKind.AUDIO)] == [2, 3]
    assert [t.id for t in info.tracks_of(TrackKind.SUBTITLE)] == [4]


def test_every_error_code_has_a_user_message() -> None:
    assert set(USER_MESSAGES) == set(ErrorCode)


def test_playback_error_keeps_code_and_detail() -> None:
    err = PlaybackError(ErrorCode.MEDIA_NOT_FOUND, "C:/nope.mkv")
    assert err.code is ErrorCode.MEDIA_NOT_FOUND
    assert err.detail == "C:/nope.mkv"
    assert "media_not_found" in str(err)
    assert err.user_message == USER_MESSAGES[ErrorCode.MEDIA_NOT_FOUND]
