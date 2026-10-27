"""libVLC adapter — M1 evaluation prototype.

Uses python-vlc against a 64-bit libVLC 3.x found by ``_engine_paths``.

Findings encoded here (see docs/milestones/M1/benchmark-report.md):
* python-vlc's ``Media.tracks_get()`` crashes the process (access violation)
  with libVLC 3.0.24 x64 + python-vlc 3.0.21203. Track codecs are read with a
  minimal ctypes struct instead.
* libVLC does not expose the active hardware decoder through its API. It is
  read from the log ("Using <api> for hardware decoding").
* libVLC event callbacks run on libVLC threads and must not call back into
  the player synchronously, so follow-up commands go through a worker thread.
"""

from __future__ import annotations

import ctypes
import os
import re
from collections import deque
from collections.abc import Mapping
from typing import Any

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.models import EngineCapabilities, MediaInfo, PlaybackState, TrackInfo, TrackKind
from babarify_frame.playback.adapters._engine_paths import add_dll_dir, find_vlc_dir
from babarify_frame.playback.contracts import EngineBase
from babarify_frame.playback.factory import EngineProbe

S = PlaybackState
_HW_RE = re.compile(r"Using (.+?) for hardware decoding")
_VOUT_RE = re.compile(r'using (?:vout display|video output) module "([^"]+)"')
_FOURCC_NAMES = {
    "h264": "h264",
    "hevc": "hevc",
    "VP90": "vp9",
    "av01": "av1",
    "mp4a": "aac",
    "a52 ": "ac3",
    "Opus": "opus",
    "subt": "subrip",
    "ssa ": "ass",
}


def _load_vlc() -> Any:
    vlc_dir = find_vlc_dir()
    if vlc_dir is None:
        raise PlaybackError(
            ErrorCode.ENGINE_UNAVAILABLE, "64-bit libvlc.dll not found (.engines/vlc or BABARIFY_VLC_DIR)"
        )
    add_dll_dir(vlc_dir)
    os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(vlc_dir / "libvlc.dll"))
    os.environ.setdefault("PYTHON_VLC_MODULE_PATH", str(vlc_dir / "plugins"))
    import vlc

    return vlc


def probe() -> EngineProbe:
    try:
        vlc = _load_vlc()
    except PlaybackError as exc:
        return EngineProbe("libvlc", False, detail=exc.detail)
    return EngineProbe("libvlc", True, vlc.libvlc_get_version().decode(), str(find_vlc_dir()))


class _RawTrack(ctypes.Structure):
    # Leading fields of libvlc_media_track_t (libVLC 3.x), enough to read codec and type safely.
    _fields_ = [
        ("codec", ctypes.c_uint32),
        ("original_fourcc", ctypes.c_uint32),
        ("id", ctypes.c_int),
        ("type", ctypes.c_int),
    ]


class _RawStats(ctypes.Structure):
    # libvlc_media_stats_t (libVLC 3.x)
    _fields_ = [
        ("read_bytes", ctypes.c_int),
        ("input_bitrate", ctypes.c_float),
        ("demux_read_bytes", ctypes.c_int),
        ("demux_bitrate", ctypes.c_float),
        ("demux_corrupted", ctypes.c_int),
        ("demux_discontinuity", ctypes.c_int),
        ("decoded_video", ctypes.c_int),
        ("decoded_audio", ctypes.c_int),
        ("displayed_pictures", ctypes.c_int),
        ("lost_pictures", ctypes.c_int),
        ("played_abuffers", ctypes.c_int),
        ("lost_abuffers", ctypes.c_int),
        ("sent_packets", ctypes.c_int),
        ("sent_bytes", ctypes.c_int),
        ("send_bitrate", ctypes.c_float),
    ]


class LibVlcEngine(EngineBase):
    name = "libvlc"

    def __init__(self, extra_args: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._extra_args = extra_args
        self._vlc: Any = None
        self._instance: Any = None
        self._player: Any = None
        self._media: Any = None
        self._log_cb: Any = None
        self._log: deque[str] = deque(maxlen=300)
        self._hwdec: str | None = None
        self._vout: str | None = None
        self._stop_requested = False
        self._version = ""
        self._info_pending = False

    # ------------------------------------------------------------ setup
    def _do_initialize(self) -> None:
        vlc = self._vlc = _load_vlc()
        args = ["--no-video-title-show", "--avcodec-hw=any", *self._extra_args]
        self._instance = vlc.Instance(args)
        if self._instance is None:
            raise PlaybackError(ErrorCode.ENGINE_UNAVAILABLE, "libvlc_new failed (plugins missing?)")
        self._install_log_callback()
        self._player = self._instance.media_player_new()
        self._version = vlc.libvlc_get_version().decode()
        events = self._player.event_manager()
        E = vlc.EventType
        for event_type, handler in (
            (E.MediaPlayerPlaying, self._on_playing),
            (E.MediaPlayerPaused, self._on_paused),
            (E.MediaPlayerStopped, self._on_stopped),
            (E.MediaPlayerEndReached, self._on_end),
            (E.MediaPlayerEncounteredError, self._on_error),
            (E.MediaPlayerTimeChanged, self._on_time),
            (E.MediaPlayerLengthChanged, self._on_length),
            (E.MediaPlayerBuffering, self._on_buffering),
        ):
            events.event_attach(event_type, handler)

    def _install_log_callback(self) -> None:
        vsnprintf = ctypes.cdll.msvcrt._vsnprintf
        vsnprintf.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_void_p]

        @self._vlc.CallbackDecorators.LogCb  # type: ignore[untyped-decorator]
        def on_log(_data: Any, level: int, _ctx: Any, fmt: bytes, args: Any) -> None:
            try:
                buf = ctypes.create_string_buffer(1024)
                vsnprintf(buf, 1023, fmt, args)
                text = buf.value.decode("utf-8", "replace")
                self._log.append(f"{level} {text}")
                if (m := _HW_RE.search(text)) is not None:
                    self._hwdec = m.group(1)
                elif (m := _VOUT_RE.search(text)) is not None:
                    self._vout = m.group(1)
            except Exception:  # never let an exception cross into libVLC
                pass

        self._log_cb = on_log  # keep a reference: libVLC holds a raw pointer
        self._instance.log_set(on_log, None)

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            engine_name="libvlc",
            engine_version=self._version,
            min_rate=0.25,
            max_rate=4.0,
            max_volume=200,
            supports_audio_tracks=True,
            supports_subtitle_tracks=True,
            supports_embedding=True,
            hardware_decoding="requested",
            notes=("Prototype: seeking after end of media is not implemented.",),
        )

    def diagnostics(self) -> Mapping[str, str]:
        return {
            "engine": f"libVLC {self._version}",
            "hwdec": self._hwdec or "none reported (software decoding or not yet decoding)",
            "video_output": self._vout or "unknown",
            "log_errors": str(sum(1 for line in self._log if line.startswith("4 "))),
        }

    def recent_log(self) -> list[str]:
        return list(self._log)

    def playback_stats(self) -> dict[str, int]:
        """Frame counters for the current media (cumulative since open)."""
        if self._media is None:
            return {}
        fn = self._vlc.dll.libvlc_media_get_stats
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RawStats)]
        fn.restype = ctypes.c_int
        stats = _RawStats()
        if not fn(self._media._as_parameter_, ctypes.byref(stats)):
            return {}
        return {
            "decoded_video": stats.decoded_video,
            "decoded_audio": stats.decoded_audio,
            "displayed": stats.displayed_pictures,
            "dropped": stats.lost_pictures,
            "lost_audio_buffers": stats.lost_abuffers,
        }

    # ---------------------------------------------------------- commands
    def _do_set_video_output(self, window_id: int | None) -> None:
        self._player.set_hwnd(window_id or None)

    def _do_open(self, uri: str, autoplay: bool) -> None:
        self._stop_requested = False
        self._hwdec = None
        self._info_pending = True
        old = self._media
        self._media = self._instance.media_new_path(uri)
        self._player.set_media(self._media)
        if old is not None:
            old.release()
        if self._player.play() != 0:
            self._fail(PlaybackError(ErrorCode.MEDIA_OPEN_FAILED, self._last_error()))

    def _do_play(self) -> None:
        state = self.state
        if state is S.PAUSED:
            self._player.set_pause(0)
        elif state is S.ENDED:
            self._info_pending = True
            self._player.play()

    def _do_pause(self) -> None:
        if self.state in (S.PLAYING, S.BUFFERING):
            self._player.set_pause(1)

    def _do_stop(self) -> None:
        self._stop_requested = True
        self._player.stop()  # synchronous in libVLC 3
        self._set_position(0)
        self._transition(S.READY)

    def _do_seek(self, position_ms: int) -> None:
        if self.state is S.ENDED:
            raise PlaybackError(ErrorCode.UNSUPPORTED, "libVLC prototype cannot seek after end of media")
        self._player.set_time(position_ms)
        if self.state is S.PAUSED:
            # libVLC sends no TimeChanged while paused, so report the accepted target ourselves.
            self._set_position(position_ms)

    def _do_set_volume(self, level: int) -> None:
        self._player.audio_set_volume(level)

    def _do_set_muted(self, enabled: bool) -> None:
        self._player.audio_set_mute(enabled)

    def _do_set_rate(self, rate: float) -> None:
        self._player.set_rate(rate)

    def _do_close(self) -> None:
        try:
            # Detach the Python log callback first: libVLC threads (including the video
            # window thread) must stop calling into Python while we tear down.
            if self._instance is not None:
                self._instance.log_unset()
            if self._player is not None:
                self._stop_requested = True
                self._player.stop()
                self._player.release()
            if self._media is not None:
                self._media.release()
            if self._instance is not None:
                self._instance.release()
        finally:
            self._player = self._media = self._instance = None

    # ------------------------------------------------- libVLC callbacks
    # These run on libVLC threads: update state only, defer player calls.
    def _on_playing(self, _event: Any) -> None:
        if self._info_pending:
            self._info_pending = False
            self._defer(self._collect_media_info)
        if self.state is S.LOADING and not self._autoplay:
            self._defer(self._player.set_pause, 1)  # Paused event moves us to PAUSED
            return
        self._transition(S.PLAYING)

    def _on_paused(self, _event: Any) -> None:
        self._transition(S.PAUSED)

    def _on_stopped(self, _event: Any) -> None:
        if self._stop_requested and self.state is not S.CLOSED:
            self._transition(S.READY)

    def _on_end(self, _event: Any) -> None:
        self._defer(self._finish_end)

    def _finish_end(self) -> None:
        # libVLC reports unreadable files as Playing -> EndReached with no error event
        # (it falls back to the MPEG-PS demuxer). Nothing decoded means the open failed.
        stats = self.playback_stats()
        decoded = stats.get("decoded_video", 0) + stats.get("decoded_audio", 0)
        if self.get_playback_state().position_ms == 0 and decoded == 0:
            self._fail(PlaybackError(ErrorCode.MEDIA_OPEN_FAILED, self._last_error()))
        else:
            self._end_reached()

    def _on_error(self, _event: Any) -> None:
        code = ErrorCode.MEDIA_OPEN_FAILED if self.state is S.LOADING else ErrorCode.ENGINE_FAILURE
        self._fail(PlaybackError(code, self._last_error()))

    def _on_time(self, event: Any) -> None:
        self._set_position(event.u.new_time)

    def _on_length(self, event: Any) -> None:
        self._set_duration(event.u.new_length)

    def _on_buffering(self, event: Any) -> None:
        cache = event.u.new_cache
        state = self.state
        if state is S.PLAYING and cache < 100:
            self._transition(S.BUFFERING)
        elif state is S.BUFFERING and cache >= 100:
            self._transition(S.PLAYING)

    # ------------------------------------------------------------ helpers
    def _last_error(self) -> str:
        errors = [line for line in self._log if line.startswith("4 ")]
        return errors[-1] if errors else "libVLC reported an error"

    def _read_tracks(self) -> list[tuple[int, int, str]]:
        dll = self._vlc.dll
        get, release = dll.libvlc_media_tracks_get, dll.libvlc_media_tracks_release
        get.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_RawTrack)))]
        get.restype = ctypes.c_uint
        release.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        array = ctypes.POINTER(ctypes.POINTER(_RawTrack))()
        handle = self._media._as_parameter_
        count = get(handle, ctypes.byref(array))
        try:
            out = []
            for i in range(count):
                t = array[i].contents
                fourcc = t.codec.to_bytes(4, "little").decode("latin-1")
                out.append((t.id, t.type, _FOURCC_NAMES.get(fourcc, fourcc.strip())))
            return out
        finally:
            if count:
                release(array, count)

    def _collect_media_info(self) -> None:
        player, media = self._player, self._media
        if player is None or media is None:
            return
        try:
            kinds = {0: TrackKind.AUDIO, 1: TrackKind.VIDEO, 2: TrackKind.SUBTITLE}
            raw = self._read_tracks()
            audio_sel, spu_sel = player.audio_get_track(), player.video_get_spu()
            names = {
                tid: (desc or b"").decode("utf-8", "replace")
                for tid, desc in (player.audio_get_track_description() or [])
                + (player.video_get_spu_description() or [])
            }
            tracks = tuple(
                TrackInfo(
                    id=tid,
                    kind=kinds[ttype],
                    title=names.get(tid),
                    codec=codec,
                    selected=(
                        kinds[ttype] is TrackKind.VIDEO
                        or (kinds[ttype] is TrackKind.AUDIO and tid == audio_sel)
                        or (kinds[ttype] is TrackKind.SUBTITLE and tid == spu_sel)
                    ),
                )
                for tid, ttype, codec in raw
                if ttype in kinds
            )
            width, height = player.video_get_size(0) or (0, 0)
            video = next((t for t in tracks if t.kind is TrackKind.VIDEO), None)
            audio = next((t for t in tracks if t.kind is TrackKind.AUDIO), None)
            self._set_media_info(
                MediaInfo(
                    uri=self._uri or "",
                    duration_ms=player.get_length() or None,
                    video_codec=video.codec if video else None,
                    width=width or None,
                    height=height or None,
                    frame_rate=player.get_fps() or None,
                    audio_codec=audio.codec if audio else None,
                    tracks=tracks,
                )
            )
        except Exception as exc:  # diagnostics must never break playback
            self._log.append(f"4 babarify: media info failed: {exc!r}")
