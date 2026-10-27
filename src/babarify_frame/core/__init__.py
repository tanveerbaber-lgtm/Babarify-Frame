"""Engine-independent models, errors and events shared by every layer."""

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import (
    EndReached,
    ErrorOccurred,
    MediaInfoChanged,
    PlaybackEvent,
    PositionChanged,
    StateChanged,
)
from babarify_frame.core.models import (
    EngineCapabilities,
    MediaInfo,
    PlaybackState,
    PlaybackStatus,
    TrackInfo,
    TrackKind,
)

__all__ = [
    "EndReached",
    "EngineCapabilities",
    "ErrorCode",
    "ErrorOccurred",
    "MediaInfo",
    "MediaInfoChanged",
    "PlaybackError",
    "PlaybackEvent",
    "PlaybackState",
    "PlaybackStatus",
    "PositionChanged",
    "StateChanged",
    "TrackInfo",
    "TrackKind",
]
