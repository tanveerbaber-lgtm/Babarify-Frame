"""Media probe contract (M6): metadata and a thumbnail for a file, without a window or sound.

Used by the library on a background thread. A probe never raises for a bad file: it returns
``None`` (unreadable) or a result with the fields it could determine.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

THUMBNAIL_WIDTH = 320


@dataclass(frozen=True)
class ProbeResult:
    duration_ms: int | None
    width: int | None
    height: int | None
    video_codec: str | None
    audio_codec: str | None
    # Thumbnail as 32-bit BGRX pixels (QImage.Format_RGB32 on little-endian), or None.
    thumbnail: bytes | None = None
    thumbnail_width: int = 0
    thumbnail_height: int = 0
    # The file's own tags, when it has them.
    title: str | None = None
    artist: str | None = None
    album: str | None = None


class MediaProbe(ABC):
    name = "probe"

    @abstractmethod
    def probe(self, path: str, cancel: threading.Event) -> ProbeResult | None: ...

    def close(self) -> None:  # noqa: B027  (optional hook, most probes hold nothing)
        """Release engine resources. Safe to call more than once."""
