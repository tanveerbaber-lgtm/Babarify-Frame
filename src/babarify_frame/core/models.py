"""Typed playback models. Immutable so they can cross threads safely."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PlaybackState(Enum):
    UNINITIALIZED = "uninitialized"
    READY = "ready"  # engine initialised, nothing playing
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    BUFFERING = "buffering"
    ENDED = "ended"
    ERROR = "error"
    CLOSED = "closed"


class TrackKind(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"


@dataclass(frozen=True)
class TrackInfo:
    id: int
    kind: TrackKind
    title: str | None = None
    language: str | None = None
    codec: str | None = None
    selected: bool = False


@dataclass(frozen=True)
class MediaInfo:
    uri: str
    duration_ms: int | None = None
    video_codec: str | None = None
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    audio_codec: str | None = None
    tracks: tuple[TrackInfo, ...] = ()

    def tracks_of(self, kind: TrackKind) -> tuple[TrackInfo, ...]:
        return tuple(t for t in self.tracks if t.kind is kind)


@dataclass(frozen=True)
class EngineCapabilities:
    """What an engine can do. The UI must disable or explain anything reported False."""

    engine_name: str
    engine_version: str
    can_seek: bool = True
    can_change_rate: bool = True
    min_rate: float = 0.25
    max_rate: float = 4.0
    max_volume: int = 100
    supports_audio_tracks: bool = False
    supports_subtitle_tracks: bool = False
    supports_embedding: bool = False  # can render into a host window handle
    hardware_decoding: str = "unknown"  # "unknown" | "requested" | "unavailable"
    notes: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class PlaybackStatus:
    state: PlaybackState
    position_ms: int = 0
    duration_ms: int | None = None
    volume: int = 100
    muted: bool = False
    rate: float = 1.0
    uri: str | None = None
