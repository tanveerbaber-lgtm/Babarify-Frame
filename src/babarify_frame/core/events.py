"""Normalised engine events.

Engines may emit these from their own threads. Consumers that touch the UI
must marshal them to the UI thread (see ``ui.bridge``).
"""

from __future__ import annotations

from dataclasses import dataclass

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.models import MediaInfo, PlaybackState


@dataclass(frozen=True)
class StateChanged:
    old: PlaybackState
    new: PlaybackState


@dataclass(frozen=True)
class PositionChanged:
    position_ms: int


@dataclass(frozen=True)
class MediaInfoChanged:
    info: MediaInfo


@dataclass(frozen=True)
class ErrorOccurred:
    error: PlaybackError


@dataclass(frozen=True)
class EndReached:
    uri: str


@dataclass(frozen=True)
class Notice:
    """A non-fatal problem the user should hear about (playback continues), e.g. an unreadable
    subtitle file."""

    code: ErrorCode
    message: str


PlaybackEvent = StateChanged | PositionChanged | MediaInfoChanged | ErrorOccurred | EndReached | Notice
