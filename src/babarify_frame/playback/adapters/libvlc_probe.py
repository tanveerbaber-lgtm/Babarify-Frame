"""libVLC media probe (M6): metadata via preparsing, thumbnail via memory video callbacks.

libVLC 3 has no thumbnail API (libVLC 4 adds one). The probe plays the file muted into a
memory buffer (no window, no sound, software decoding), keeps the second frame shown after
seeking to 10 % of the duration, and stops. Findings from the M6 spike:
* python-vlc's format-callback type passes ``chroma`` as a read-only string, so the requested
  RV32 chroma never reached libVLC (grey, quarter-width images). The callback is declared here
  with a writable pointer.
* The size libVLC offers in the format callback includes decoder padding (1090 for 1080 lines),
  so the aspect ratio comes from the parsed track; rotation metadata is already applied
  (portrait output for a 90-degree file), which is detected by comparing orientations.
* Unreadable files would otherwise wait for the timeout; error/end events stop the wait.
It uses its own shared libVLC instance (audio and on-screen text disabled), never the player's.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from typing import Any

from babarify_frame.core.models import AUDIO_EXTENSIONS
from babarify_frame.playback.adapters.libvlc import _load_vlc, _SharedInstance, read_media_tracks
from babarify_frame.playback.media_probe import THUMBNAIL_WIDTH, MediaProbe, ProbeResult

PARSE_TIMEOUT_S = 4.0
FRAME_TIMEOUT_S = 4.0
_PROBE_ARGS = ("--no-video-title-show", "--no-lua", "--no-audio", "--no-spu", "--no-osd", "--no-stats")

_FormatCb = ctypes.CFUNCTYPE(
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,  # char *chroma: writable, 4 bytes
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint),
)
_CleanupCb = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
_LockCb = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_UnlockCb = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_DisplayCb = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)


def thumbnail_size(source_w: int, source_h: int, parsed_w: int, parsed_h: int) -> tuple[int, int]:
    """Output size for a thumbnail THUMBNAIL_WIDTH wide (or narrower for tiny videos)."""
    w, h = parsed_w, parsed_h
    if not (w and h):
        w, h = source_w, source_h
    elif (source_w > source_h) != (w > h):  # rotation already applied by libVLC
        w, h = h, w
    if not (w and h):
        return THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 9 // 16
    out_w = min(THUMBNAIL_WIDTH, w)
    out_h = max(2, round(out_w * h / w / 2) * 2)
    return out_w, out_h


class LibVlcProbe(MediaProbe):
    name = "libvlc"

    def __init__(self) -> None:
        self._vlc = _load_vlc()
        self._instance = _SharedInstance.get(self._vlc, _PROBE_ARGS).instance
        self._lock = threading.Lock()  # one probe at a time per object

    def probe(self, path: str, cancel: threading.Event) -> ProbeResult | None:
        with self._lock:
            return self._probe(path, cancel)

    # ------------------------------------------------------------------
    def _probe(self, path: str, cancel: threading.Event) -> ProbeResult | None:
        vlc = self._vlc
        media = self._instance.media_new_path(path)
        if media is None:
            return None
        try:
            media.parse_with_options(vlc.MediaParseFlag.local, int(PARSE_TIMEOUT_S * 1000))
            deadline = time.monotonic() + PARSE_TIMEOUT_S
            while media.get_parsed_status() == 0 and time.monotonic() < deadline and not cancel.is_set():
                time.sleep(0.01)
            if cancel.is_set() or media.get_parsed_status() != vlc.MediaParsedStatus.done:
                return None
            duration = media.get_duration()
            tracks = read_media_tracks(vlc, media)
            video = next((t for t in tracks if t.type == 1), None)
            audio = next((t for t in tracks if t.type == 0), None)
            result = ProbeResult(
                duration_ms=duration if duration and duration > 0 else None,
                width=video.width or None if video else None,
                height=video.height or None if video else None,
                video_codec=video.codec if video else None,
                audio_codec=audio.codec if audio else None,
            )
            audio_only = video is None and (
                bool(tracks) or os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS
            )
            if audio_only:
                return result
            return self._thumbnail(media, result, cancel)
        finally:
            media.release()

    def _thumbnail(self, media: Any, result: ProbeResult, cancel: threading.Event) -> ProbeResult | None:
        vlc = self._vlc
        state: dict[str, Any] = {"w": 0, "h": 0, "buf": None, "frames": 0, "src": (0, 0)}
        done = threading.Event()
        shown = threading.Event()
        parsed_w, parsed_h = result.width or 0, result.height or 0

        @_FormatCb  # type: ignore[untyped-decorator]
        def setup(_opaque: Any, chroma: int, width: Any, height: Any, pitches: Any, lines: Any) -> int:
            out_w, out_h = thumbnail_size(width[0], height[0], parsed_w, parsed_h)
            ctypes.memmove(chroma, b"RV32", 4)
            state.update(
                w=out_w, h=out_h, src=(width[0], height[0]), buf=(ctypes.c_ubyte * (out_w * out_h * 4))()
            )
            width[0], height[0] = out_w, out_h
            pitches[0], lines[0] = out_w * 4, out_h
            return 1

        @_CleanupCb  # type: ignore[untyped-decorator]
        def cleanup(_opaque: Any) -> None:
            pass

        @_LockCb  # type: ignore[untyped-decorator]
        def lock(_opaque: Any, planes: Any) -> None:
            planes[0] = ctypes.cast(state["buf"], ctypes.c_void_p)
            return None

        @_UnlockCb  # type: ignore[untyped-decorator]
        def unlock(_opaque: Any, _picture: Any, _planes: Any) -> None:
            pass

        @_DisplayCb  # type: ignore[untyped-decorator]
        def display(_opaque: Any, _picture: Any) -> None:
            state["frames"] += 1
            if state["frames"] >= 2:  # the first frame after a seek can be a partial one
                shown.set()
                done.set()

        start_s = result.duration_ms / 10_000 if result.duration_ms else 1.0
        media.add_option(f":start-time={start_s:.2f}")
        media.add_option(":avcodec-hw=none")
        media.add_option(":no-audio")
        player = self._instance.media_player_new()
        dll = vlc.dll
        set_callbacks = dll.libvlc_video_set_callbacks
        set_callbacks.argtypes = [ctypes.c_void_p, _LockCb, _UnlockCb, _DisplayCb, ctypes.c_void_p]
        set_format = dll.libvlc_video_set_format_callbacks
        set_format.argtypes = [ctypes.c_void_p, _FormatCb, _CleanupCb]
        set_callbacks(player._as_parameter_, lock, unlock, display, None)
        set_format(player._as_parameter_, setup, cleanup)
        events = player.event_manager()

        def stop_waiting(_event: Any) -> None:
            done.set()

        for kind in (vlc.EventType.MediaPlayerEncounteredError, vlc.EventType.MediaPlayerEndReached):
            events.event_attach(kind, stop_waiting)
        try:
            player.set_media(media)
            player.play()
            deadline = time.monotonic() + FRAME_TIMEOUT_S
            while not done.wait(0.05):
                if cancel.is_set() or time.monotonic() > deadline:
                    break
            length = player.get_length()
            player.stop()
        finally:
            for kind in (vlc.EventType.MediaPlayerEncounteredError, vlc.EventType.MediaPlayerEndReached):
                events.event_detach(kind)
            player.release()
        if not shown.is_set():
            # No picture: unreadable, or nothing decodable. Keep what parsing found, if anything.
            return result if (result.video_codec or result.audio_codec) else None
        src_w, src_h = state["src"]
        return ProbeResult(
            duration_ms=result.duration_ms or (length if length and length > 0 else None),
            width=result.width or src_w or None,
            height=result.height or src_h or None,
            video_codec=result.video_codec,
            audio_codec=result.audio_codec,
            thumbnail=bytes(state["buf"]),
            thumbnail_width=state["w"],
            thumbnail_height=state["h"],
        )
