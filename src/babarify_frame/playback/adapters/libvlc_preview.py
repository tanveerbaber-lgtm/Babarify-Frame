"""libVLC seek-bar previews (M8): a second, muted, windowless player decodes into memory.

The player opens the file paused (software decoding, no audio, no subtitles) and each
request seeks it; the first frame delivered after the seek is the preview. It uses the
probe's shared instance (R20), with the same writable-chroma callbacks (R26).
"""

from __future__ import annotations

import ctypes
import threading
import time
from typing import Any

from babarify_frame.playback.adapters.libvlc import _load_vlc, _SharedInstance
from babarify_frame.playback.adapters.libvlc_probe import (
    _PROBE_ARGS,
    _CleanupCb,
    _DisplayCb,
    _FormatCb,
    _LockCb,
    _UnlockCb,
)
from babarify_frame.playback.preview import PREVIEW_WIDTH, FramePreview, PreviewFrame

OPEN_TIMEOUT_S = 4.0
FRAME_TIMEOUT_S = 2.0


class LibVlcPreview(FramePreview):
    def __init__(self) -> None:
        self._vlc = _load_vlc()
        self._instance = _SharedInstance.get(self._vlc, _PROBE_ARGS).instance
        self._player: Any = None
        self._media: Any = None
        self._buf: Any = None
        self._size = (0, 0)
        self._frames = 0
        self._latest = b""
        self._cond = threading.Condition()
        self._callbacks = self._make_callbacks()  # kept alive: libVLC holds raw pointers

    def _make_callbacks(self) -> tuple[Any, ...]:
        @_FormatCb  # type: ignore[untyped-decorator]
        def setup(_opaque: Any, chroma: int, width: Any, height: Any, pitches: Any, lines: Any) -> int:
            # libVLC's size includes decoder padding (1090 lines for 1080): under 1 % off.
            w = max(2, min(PREVIEW_WIDTH, width[0]))
            h = max(2, round(w * height[0] / max(1, width[0]) / 2) * 2)
            ctypes.memmove(chroma, b"RV32", 4)
            self._size = (w, h)
            self._buf = (ctypes.c_ubyte * (w * h * 4))()
            width[0], height[0] = w, h
            pitches[0], lines[0] = w * 4, h
            return 1

        @_CleanupCb  # type: ignore[untyped-decorator]
        def cleanup(_opaque: Any) -> None:
            pass

        @_LockCb  # type: ignore[untyped-decorator]
        def lock(_opaque: Any, planes: Any) -> None:
            planes[0] = ctypes.cast(self._buf, ctypes.c_void_p)
            return None

        @_UnlockCb  # type: ignore[untyped-decorator]
        def unlock(_opaque: Any, _picture: Any, _planes: Any) -> None:
            pass

        @_DisplayCb  # type: ignore[untyped-decorator]
        def display(_opaque: Any, _picture: Any) -> None:
            data = bytes(self._buf)
            with self._cond:
                self._latest = data
                self._frames += 1
                self._cond.notify_all()

        return setup, cleanup, lock, unlock, display

    def _wait_frame(self, after: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._frames <= after:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(left)
            return True

    def open(self, path: str) -> bool:
        self.close()
        vlc = self._vlc
        media = self._instance.media_new_path(path)
        if media is None:
            return False
        for option in (":avcodec-hw=none", ":no-audio", ":no-spu", ":no-sub-autodetect-file"):
            media.add_option(option)
        player = self._instance.media_player_new()
        dll = vlc.dll
        set_callbacks = dll.libvlc_video_set_callbacks
        set_callbacks.argtypes = [ctypes.c_void_p, _LockCb, _UnlockCb, _DisplayCb, ctypes.c_void_p]
        set_format = dll.libvlc_video_set_format_callbacks
        set_format.argtypes = [ctypes.c_void_p, _FormatCb, _CleanupCb]
        setup, cleanup, lock, unlock, display = self._callbacks
        set_callbacks(player._as_parameter_, lock, unlock, display, None)
        set_format(player._as_parameter_, setup, cleanup)
        player.set_media(media)
        self._player, self._media = player, media
        with self._cond:
            self._frames = 0
        player.play()
        if not self._wait_frame(0, OPEN_TIMEOUT_S):
            self.close()
            return False
        player.set_pause(1)
        return True

    def frame_at(self, position_ms: int) -> PreviewFrame | None:
        player = self._player
        if player is None:
            return None
        with self._cond:
            before = self._frames
        player.set_time(max(0, int(position_ms)))
        if not self._wait_frame(before, FRAME_TIMEOUT_S):
            return None
        with self._cond:
            data = self._latest
        w, h = self._size
        if len(data) != w * h * 4:
            return None
        return PreviewFrame(position_ms, w, h, data)

    def close(self) -> None:
        player, media = self._player, self._media
        self._player = self._media = None
        if player is not None:
            player.stop()
            player.release()
        if media is not None:
            media.release()
