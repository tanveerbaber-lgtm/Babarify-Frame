"""Engine-independent models, errors and events shared by every layer."""

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import (
    EndReached,
    ErrorOccurred,
    MediaInfoChanged,
    Notice,
    PlaybackEvent,
    PositionChanged,
    StateChanged,
)
from babarify_frame.core.models import (
    EngineCapabilities,
    EngineOptions,
    MediaInfo,
    PlaybackState,
    PlaybackStatus,
    SubtitlePosition,
    SubtitleStyle,
    TrackInfo,
    TrackKind,
)

__all__ = [
    "EndReached",
    "EngineCapabilities",
    "EngineOptions",
    "ErrorCode",
    "ErrorOccurred",
    "MediaInfo",
    "MediaInfoChanged",
    "Notice",
    "PlaybackError",
    "PlaybackEvent",
    "PlaybackState",
    "PlaybackStatus",
    "PositionChanged",
    "StateChanged",
    "SubtitlePosition",
    "SubtitleStyle",
    "TrackInfo",
    "TrackKind",
]
