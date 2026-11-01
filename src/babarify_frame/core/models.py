"""Typed playback models. Immutable so they can cross threads safely."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from babarify_frame.core.enhancements import VideoTransform


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
    # Details for the media information panel (M8); 0 = not reported by the engine.
    width: int = 0
    height: int = 0
    frame_rate: float = 0.0
    channels: int = 0
    sample_rate: int = 0
    bitrate: int = 0  # bits per second


@dataclass(frozen=True)
class Chapter:
    """A chapter of the file (M8). Chapters are sorted by start and do not overlap."""

    index: int
    start_ms: int
    title: str = ""

    @property
    def label(self) -> str:
        return self.title or f"Chapter {self.index + 1}"


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
    chapters: tuple[Chapter, ...] = ()  # M8
    metadata: tuple[tuple[str, str], ...] = ()  # (label, value) from the file's tags, e.g. ("Title", ...)

    def tracks_of(self, kind: TrackKind) -> tuple[TrackInfo, ...]:
        return tuple(t for t in self.tracks if t.kind is kind)

    def chapter_at(self, position_ms: int) -> Chapter | None:
        current = None
        for chapter in self.chapters:
            if chapter.start_ms <= position_ms:
                current = chapter
        return current


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
    supports_external_subtitles: bool = False
    supports_dual_subtitles: bool = False  # two subtitle tracks at once; no current engine offers it
    # How a subtitle style change takes effect: "live", "restart" (new engine) or "unsupported".
    subtitle_style: str = "unsupported"
    max_delay_ms: int = 60_000  # |audio/subtitle delay| limit
    # What was configured, not what is in use: "requested" | "disabled" | "unavailable" | "unknown".
    # The decoder actually in use is reported per media by diagnostics()["decoder"].
    hardware_decoding: str = "unknown"
    # Picture and sound (M7). Each flag says the control changes real output on this engine.
    picture_adjustments: frozenset[str] = frozenset()  # subset of PICTURE_RANGES names
    supports_aspect_ratio: bool = False
    supports_crop: bool = False
    supports_zoom: bool = False
    rotation: str = "unsupported"  # "live", "restart" or "unsupported", like subtitle_style
    supports_equalizer: bool = False
    equalizer_presets: tuple[str, ...] = ()
    equalizer_bands_hz: tuple[int, ...] = ()
    supports_frame_step: bool = False
    supports_frame_back_step: bool = False
    supports_snapshot: bool = False
    # Advanced media (M8)
    network_schemes: frozenset[str] = frozenset()  # subset of core.network.STREAM_SCHEMES
    supports_chapters: bool = False  # MediaInfo.chapters is filled when the file has chapters
    notes: tuple[str, ...] = field(default=())


class SubtitlePosition(Enum):
    BOTTOM = "bottom"
    SLIGHTLY_RAISED = "slightly_raised"
    RAISED = "raised"
    HIGH = "high"


# Media files the library scans (M6); other extensions are ignored, so a scanned folder never
# pulls in documents, images or subtitle files.
VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".ts", ".mts", ".m2ts",
        ".mpg", ".mpeg", ".vob", ".ogv", ".flv", ".3gp",
    }
)  # fmt: skip
AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".wma", ".ac3", ".mka"}
)
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
SUBTITLE_EXTENSIONS = frozenset({".srt", ".ass", ".ssa", ".vtt", ".sub", ".smi", ".sami", ".txt", ".idx"})
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class SubtitleStyle:
    """Look of plain-text subtitles (SRT, WebVTT, MicroDVD...). ASS/SSA keep their own styling."""

    font_family: str = ""  # "" = engine default
    size_pct: int = 100  # 50..200 % of the engine's normal size
    text_color: str = "#FFFFFF"
    background_opacity: int = 0  # 0..100 %
    position: SubtitlePosition = SubtitlePosition.BOTTOM

    def normalized(self) -> SubtitleStyle:
        return replace(
            self,
            font_family=self.font_family.strip()[:100],
            size_pct=max(50, min(200, self.size_pct)),
            text_color=self.text_color.upper() if _COLOR.match(self.text_color) else "#FFFFFF",
            background_opacity=max(0, min(100, self.background_opacity)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "font_family": self.font_family,
            "size_pct": self.size_pct,
            "text_color": self.text_color,
            "background_opacity": self.background_opacity,
            "position": self.position.value,
        }

    @classmethod
    def from_dict(cls, data: Any) -> SubtitleStyle:
        """Build from untrusted data; invalid fields fall back to defaults."""
        if not isinstance(data, dict):
            return cls()
        d = cls()
        font = data.get("font_family", d.font_family)
        size = data.get("size_pct", d.size_pct)
        color = data.get("text_color", d.text_color)
        opacity = data.get("background_opacity", d.background_opacity)
        try:
            position = SubtitlePosition(data.get("position", d.position.value))
        except ValueError:
            position = d.position
        return cls(
            font_family=font if isinstance(font, str) else d.font_family,
            size_pct=size if isinstance(size, int) and not isinstance(size, bool) else d.size_pct,
            text_color=color if isinstance(color, str) else d.text_color,
            background_opacity=opacity if isinstance(opacity, int) and not isinstance(opacity, bool) else 0,
            position=position,
        ).normalized()


@dataclass(frozen=True)
class EngineOptions:
    """Engine construction options. Changing them requires creating a new engine."""

    hardware_decoding: bool = True  # allow GPU decoding when the engine and hardware support it
    subtitle_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    video_transform: VideoTransform = VideoTransform.NONE  # rotation/flip (M7)


@dataclass(frozen=True)
class PlaybackStatus:
    state: PlaybackState
    position_ms: int = 0
    duration_ms: int | None = None
    volume: int = 100
    muted: bool = False
    rate: float = 1.0
    uri: str | None = None
    audio_delay_ms: int = 0  # positive = audio later
    subtitle_delay_ms: int = 0  # positive = subtitles later
