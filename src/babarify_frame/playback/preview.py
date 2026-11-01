"""Seek-bar preview contract (M8): a small picture of the file at a given time.

A preview source works on its own decoder, never the player's, so hovering over the seek bar
cannot disturb playback. It is used from one background thread; ``frame_at`` may take up to
about a second on 4K files (M8 spike: 25-240 ms at 1080p, up to 1.2 s at 2160p).
Previews are offered for local video files only: for network streams they would download the
stream a second time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

PREVIEW_WIDTH = 192


@dataclass(frozen=True)
class PreviewFrame:
    position_ms: int
    width: int
    height: int
    data: bytes  # width * height * 4 bytes, BGRA (Qt's Format_RGB32)


class FramePreview(ABC):
    @abstractmethod
    def open(self, path: str) -> bool:
        """Prepare previews for a local file; False if it has no picture or cannot be read."""

    @abstractmethod
    def frame_at(self, position_ms: int) -> PreviewFrame | None: ...

    @abstractmethod
    def close(self) -> None: ...
