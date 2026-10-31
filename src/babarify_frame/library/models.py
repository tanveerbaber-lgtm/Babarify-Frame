"""Library, history and playlist records (M6). Plain data; the database owns persistence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from babarify_frame.core.models import AUDIO_EXTENSIONS, MEDIA_EXTENSIONS, VIDEO_EXTENSIONS

__all__ = ["AUDIO_EXTENSIONS", "MEDIA_EXTENSIONS", "VIDEO_EXTENSIONS"]


def path_key(path: str) -> str:
    """Identity of a file path: absolute, normalised separators and (on Windows) case.

    ``C:/Movies/a.MKV`` and ``c:\\movies\\a.mkv`` are the same file and get the same key."""
    if "://" in path:  # a URI (e.g. the test engine's mock://) is its own identity
        return path
    return os.path.normcase(os.path.abspath(path))


class SortOrder(Enum):
    NAME = "name"
    DATE_ADDED = "date_added"
    RECENTLY_PLAYED = "recently_played"
    DURATION = "duration"
    SIZE = "size"


@dataclass(frozen=True)
class LibraryFolder:
    id: int
    path: str
    added_at: float
    available: bool = True  # False when the folder (e.g. a removable drive) is not reachable


@dataclass(frozen=True)
class MediaEntry:
    id: int
    path: str
    name: str
    folder_id: int | None
    size: int
    mtime: float
    added_at: float
    available: bool = True
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    thumbnail: str | None = None  # file name inside the thumbnail folder
    probed: bool = False
    content_key: str | None = None
    duplicates: int = 0  # other library entries with the same content
    position_ms: int = 0  # from history, when known
    last_played_at: float | None = None

    @property
    def is_video(self) -> bool:
        return bool(self.video_codec) or (
            not self.probed and os.path.splitext(self.name)[1].lower() in VIDEO_EXTENSIONS
        )


@dataclass(frozen=True)
class HistoryEntry:
    path: str
    title: str
    position_ms: int
    duration_ms: int | None
    finished: bool
    play_count: int
    last_played_at: float
    available: bool = True
    thumbnail: str | None = None

    @property
    def progress(self) -> float:
        if not self.duration_ms:
            return 0.0
        return max(0.0, min(1.0, self.position_ms / self.duration_ms))


@dataclass(frozen=True)
class Playlist:
    id: int
    name: str
    created_at: float
    item_count: int = 0


@dataclass(frozen=True)
class PlaylistItem:
    id: int
    playlist_id: int
    position: int
    path: str
    title: str
    available: bool = True
