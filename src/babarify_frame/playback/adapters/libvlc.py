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
* libVLC fires "Playing" before it knows a file is readable, and reports
  unreadable files as Playing -> EndReached without an error. The adapter holds
  LOADING until the media is confirmed (length, position or video output) and
  maps "ended with nothing decoded" to MEDIA_OPEN_FAILED.
* No TimeChanged while paused; seeking an ended player needs a restart; MPEG-TS/PS
  and Ogg report streams and video size late. Each is handled below.
* Network streams (M8): libVLC follows HTTP redirects to any scheme (file: included) and has
  no option against it, so http/https go through ``stream_proxy`` and libVLC is started with
  ``--no-lua`` (Lua playlist scripts fetch pages on their own). A server that accepts the
  connection and never answers leaves libVLC "opening" forever: an open timeout ends it.
  Remote playlists end at once with their entries as sub-items; only web/rtsp entries are
  played.
"""

from __future__ import annotations

import ctypes
import os
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, ClassVar

from babarify_frame.core.enhancements import (
    PICTURE_RANGES,
    EqualizerSettings,
    PictureSettings,
    VideoTransform,
    aspect_to_engine,
)
from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.models import (
    Chapter,
    EngineCapabilities,
    EngineOptions,
    MediaInfo,
    PlaybackState,
    SubtitlePosition,
    SubtitleStyle,
    TrackInfo,
    TrackKind,
)
from babarify_frame.core.music import AUDIO_EFFECTS
from babarify_frame.core.network import STREAM_SCHEMES, is_network_uri, uri_scheme, validate_stream_url
from babarify_frame.playback.adapters._engine_paths import add_dll_dir, find_vlc_dir
from babarify_frame.playback.contracts import EngineBase
from babarify_frame.playback.factory import EngineProbe
from babarify_frame.playback.stream_proxy import get_proxy

S = PlaybackState
_HW_RE = re.compile(r"Using (.+?) for hardware decoding")
_VOUT_RE = re.compile(r'using (?:vout display|video output) module "([^"]+)"')
# libVLC fourcc -> FFmpeg/ffprobe codec name (the vocabulary used across the app).
_FOURCC_NAMES = {
    "h264": "h264",
    "hevc": "hevc",
    "VP90": "vp9",
    "VP80": "vp8",
    "av01": "av1",
    "mp4v": "mpeg4",
    "mpgv": "mpeg2video",
    "mp2v": "mpeg2video",
    "theo": "theora",
    "WMV2": "wmv2",
    "WMV3": "wmv3",
    "mp4a": "aac",
    "a52 ": "ac3",
    "eac3": "eac3",
    "dts ": "dts",
    "mpga": "mp2",
    "mp3 ": "mp3",
    "Opus": "opus",
    "vorb": "vorbis",
    "flac": "flac",
    "s16l": "pcm_s16le",
    "WMA2": "wmav2",
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


# Named subtitle positions -> libVLC --sub-margin (pixels up from the bottom; measured in M5).
_SUB_MARGIN = {
    SubtitlePosition.BOTTOM: 0,
    SubtitlePosition.SLIGHTLY_RAISED: 60,
    SubtitlePosition.RAISED: 150,
    SubtitlePosition.HIGH: 300,
}
EXTERNAL_SUBTITLE_TIMEOUT_S = 2.5
OPEN_TIMEOUT_S = 30.0  # network streams: give up if nothing plays by then (M8)
MAX_PLAYLIST_DEPTH = 3  # a playlist entry that is itself a playlist, and so on
# Instance options for every player instance. --no-lua: Lua playlist/meta scripts would fetch
# web pages directly, around the stream proxy (M8).
BASE_ARGS = ("--no-video-title-show", "--no-lua")
# File tags shown in the media information panel (libVLC Meta name, label).
_META_FIELDS = (
    ("Title", "Title"), ("Artist", "Artist"), ("AlbumArtist", "Album artist"), ("Album", "Album"),
    ("TrackNumber", "Track"), ("Date", "Date"), ("Genre", "Genre"), ("Description", "Description"),
    ("Copyright", "Copyright"), ("Publisher", "Publisher"), ("EncodedBy", "Encoded by"),
    ("Language", "Language"), ("ShowName", "Show"), ("Season", "Season"), ("Episode", "Episode"),
    ("NowPlaying", "Now playing"),
)  # fmt: skip


def subtitle_style_args(style: SubtitleStyle) -> tuple[str, ...]:
    """libVLC 3 applies text-subtitle styling only as instance options (M5 spike: media options are
    ignored), so each distinct style needs its own shared instance."""
    style = style.normalized()
    args = [
        # freetype-rel-fontsize: font height = video height / value; 16 is "normal".
        f"--freetype-rel-fontsize={max(4, min(40, round(16 * 100 / style.size_pct)))}",
        f"--freetype-color={int(style.text_color[1:], 16)}",
        f"--freetype-background-opacity={round(style.background_opacity * 255 / 100)}",
        "--freetype-background-color=0",
        f"--sub-margin={_SUB_MARGIN[style.position]}",
    ]
    if style.font_family:
        args.append(f"--freetype-font={style.font_family}")
    return tuple(args)


def video_transform_args(transform: VideoTransform) -> tuple[str, ...]:
    """libVLC 3 rotates only through the instance-level transform filter (M7 spike: the same
    options per media are ignored), so rotation needs its own shared instance, like style."""
    if transform is VideoTransform.NONE:
        return ()
    return ("--video-filter=transform", f"--transform-type={transform.value}")


class _SharedInstance:
    """One libVLC instance per process (and argument set), shared by every engine.

    R20: each libvlc_new/libvlc_release cycle leaks ~15 handles and ~0.5 MB inside libVLC 3.0.24,
    and after ~100 instances in one process libvlc_new itself crashed (access violation). Engines
    therefore create only their own media player and media from this instance, which lives until
    the process exits. The single log callback fans lines out to the engines currently registered;
    if several engines run at the same time their diagnostics can mix (the app runs one).
    """

    _lock = threading.Lock()
    _instances: ClassVar[dict[tuple[str, ...], _SharedInstance]] = {}

    def __init__(self, vlc: Any, args: tuple[str, ...]) -> None:
        self.instance = vlc.Instance(list(args))
        if self.instance is None:
            raise PlaybackError(ErrorCode.ENGINE_UNAVAILABLE, "libvlc_new failed (plugins missing?)")
        self._sinks: list[Callable[[int, str], None]] = []
        self._sink_lock = threading.Lock()
        vsnprintf = ctypes.cdll.msvcrt._vsnprintf
        vsnprintf.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_void_p]

        @vlc.CallbackDecorators.LogCb  # type: ignore[untyped-decorator]
        def on_log(_data: Any, level: int, _ctx: Any, fmt: bytes, va: Any) -> None:
            try:
                with self._sink_lock:
                    sinks = list(self._sinks)
                if not sinks:
                    return
                buf = ctypes.create_string_buffer(1024)
                vsnprintf(buf, 1023, fmt, va)
                text = buf.value.decode("utf-8", "replace")
                for sink in sinks:
                    sink(level, text)
            except Exception:  # never let an exception cross into libVLC
                pass

        self._callback = on_log  # keep a reference: libVLC holds a raw pointer
        self.instance.log_set(on_log, None)

    @classmethod
    def get(cls, vlc: Any, args: tuple[str, ...]) -> _SharedInstance:
        with cls._lock:
            shared = cls._instances.get(args)
            if shared is None:
                shared = cls._instances[args] = cls(vlc, args)
            return shared

    def add_sink(self, sink: Callable[[int, str], None]) -> None:
        with self._sink_lock:
            self._sinks.append(sink)

    def remove_sink(self, sink: Callable[[int, str], None]) -> None:
        with self._sink_lock:
            if sink in self._sinks:
                self._sinks.remove(sink)


class _RawVideoTrack(ctypes.Structure):
    # Leading fields of libvlc_video_track_t (libVLC 3.x). Note: height comes first.
    _fields_ = [
        ("height", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("sar_num", ctypes.c_uint),
        ("sar_den", ctypes.c_uint),
        ("frame_rate_num", ctypes.c_uint),
        ("frame_rate_den", ctypes.c_uint),
    ]


class _RawAudioTrack(ctypes.Structure):
    # libvlc_audio_track_t (libVLC 3.x)
    _fields_ = [("channels", ctypes.c_uint), ("rate", ctypes.c_uint)]


class _RawChapter(ctypes.Structure):
    # libvlc_chapter_description_t (libVLC 3.x)
    _fields_ = [("time_offset", ctypes.c_int64), ("duration", ctypes.c_int64), ("name", ctypes.c_char_p)]


class _RawTrack(ctypes.Structure):
    # libvlc_media_track_t (libVLC 3.x). The union holds a pointer to the per-kind struct.
    _fields_ = [
        ("codec", ctypes.c_uint32),
        ("original_fourcc", ctypes.c_uint32),
        ("id", ctypes.c_int),
        ("type", ctypes.c_int),
        ("profile", ctypes.c_int),
        ("level", ctypes.c_int),
        ("details", ctypes.c_void_p),
        ("bitrate", ctypes.c_uint),
        ("language", ctypes.c_char_p),
        ("description", ctypes.c_char_p),
    ]


@dataclass(frozen=True)
class _Track:
    id: int
    type: int
    codec: str
    language: str | None
    width: int = 0
    height: int = 0
    fps: float = 0.0
    channels: int = 0
    rate: int = 0
    bitrate: int = 0


def read_media_tracks(vlc: Any, media: Any) -> list[_Track]:
    """Tracks of a parsed or playing media. python-vlc's ``tracks_get`` dereferences NULL union
    members (M6 spike), so the libVLC 3 structs are read directly."""
    dll = vlc.dll
    get, release = dll.libvlc_media_tracks_get, dll.libvlc_media_tracks_release
    get.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_RawTrack)))]
    get.restype = ctypes.c_uint
    release.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    array = ctypes.POINTER(ctypes.POINTER(_RawTrack))()
    count = get(media._as_parameter_, ctypes.byref(array))
    try:
        out = []
        for i in range(count):
            t = array[i].contents
            fourcc = t.codec.to_bytes(4, "little").decode("latin-1")
            lang = t.language.decode("utf-8", "replace") if t.language else None
            track = _Track(t.id, t.type, _FOURCC_NAMES.get(fourcc, fourcc.strip()), lang, bitrate=t.bitrate)
            if t.type == 1 and t.details:  # video
                v = ctypes.cast(t.details, ctypes.POINTER(_RawVideoTrack)).contents
                fps = v.frame_rate_num / v.frame_rate_den if v.frame_rate_den else 0.0
                track = replace(track, width=v.width, height=v.height, fps=fps)
            elif t.type == 0 and t.details:  # audio
                a = ctypes.cast(t.details, ctypes.POINTER(_RawAudioTrack)).contents
                track = replace(track, channels=a.channels, rate=a.rate)
            out.append(track)
        return out
    finally:
        if count:
            release(array, count)


def read_chapters(vlc: Any, player: Any) -> tuple[Chapter, ...]:
    """Chapters of the current title. python-vlc's helper never frees libVLC's array and fails
    on an error count (-1), so the libVLC 3 structs are read directly, like the tracks."""
    dll = vlc.dll
    get = dll.libvlc_media_player_get_full_chapter_descriptions
    get.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_RawChapter))),
    ]
    get.restype = ctypes.c_int
    release = dll.libvlc_chapter_descriptions_release
    release.argtypes = [ctypes.POINTER(ctypes.POINTER(_RawChapter)), ctypes.c_uint]
    array = ctypes.POINTER(ctypes.POINTER(_RawChapter))()
    count = get(player._as_parameter_, -1, ctypes.byref(array))
    if count <= 0:
        return ()
    try:
        raw = [array[i].contents for i in range(count)]
        found = sorted(
            (max(0, int(c.time_offset)), (c.name or b"").decode("utf-8", "replace").strip()) for c in raw
        )
    finally:
        release(array, count)
    return tuple(Chapter(i, start, title[:200]) for i, (start, title) in enumerate(found))


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
    allowed_schemes = frozenset({"file"}) | STREAM_SCHEMES

    def __init__(self, options: EngineOptions | None = None, extra_args: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._options = options or EngineOptions()
        self._extra_args = extra_args
        self._vlc: Any = None
        self._instance: Any = None
        self._player: Any = None
        self._media: Any = None
        self._shared: _SharedInstance | None = None
        self._log: deque[str] = deque(maxlen=300)
        self._hwdec: str | None = None
        self._vout: str | None = None
        self._stop_requested = False
        self._version = ""
        self._info_pending = False
        self._info_refresh_queued = False
        self._size_retries = 0  # media-info refreshes left while the video size is unknown
        self._last_size_retry = 0.0
        # libVLC fires "Playing" before it knows the media is readable. While LOADING we hold
        # the target state until the media is confirmed (length, position or video output).
        self._confirmed = False
        self._loading_target: PlaybackState | None = None
        self._pending_seek: int | None = None  # seek requested after end of media
        # Picture and sound (M7): kept so they survive opening another file.
        self._picture = PictureSettings()
        self._geometry: tuple[str, str, float] = ("", "", 0.0)
        self._equalizer = EqualizerSettings()
        self._eq_presets: tuple[str, ...] = ()
        self._eq_bands: tuple[int, ...] = ()
        # Network streams (M8)
        self._open_generation = 0
        self._open_started = 0.0
        self._open_timer: threading.Timer | None = None
        self._playlist_depth = 0

    # ------------------------------------------------------------ setup
    def _do_initialize(self) -> None:
        vlc = self._vlc = _load_vlc()
        style_args = subtitle_style_args(self._options.subtitle_style)
        transform_args = video_transform_args(self._options.video_transform)
        self._shared = _SharedInstance.get(vlc, (*BASE_ARGS, *style_args, *transform_args, *self._extra_args))
        self._instance = self._shared.instance
        self._shared.add_sink(self._on_log_line)
        self._player = self._instance.media_player_new()
        self._version = vlc.libvlc_get_version().decode()
        self._eq_presets = tuple(
            vlc.libvlc_audio_equalizer_get_preset_name(i).decode()
            for i in range(vlc.libvlc_audio_equalizer_get_preset_count())
        )
        self._eq_bands = tuple(
            round(vlc.libvlc_audio_equalizer_get_band_frequency(i))
            for i in range(vlc.libvlc_audio_equalizer_get_band_count())
        )
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
            (E.MediaPlayerESAdded, self._on_es_added),
            (E.MediaPlayerVout, self._on_vout),
        ):
            events.event_attach(event_type, handler)

    def _on_log_line(self, level: int, text: str) -> None:
        self._log.append(f"{level} {text}")
        if (m := _HW_RE.search(text)) is not None:
            self._hwdec = m.group(1)
        elif (m := _VOUT_RE.search(text)) is not None:
            self._vout = m.group(1)

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
            supports_external_subtitles=True,
            supports_dual_subtitles=False,  # libVLC 3 renders one subtitle track at a time
            # M7 spike (screen pixels): all five work with software decoding; with hardware
            # decoding (D3D11 video processor) gamma has no effect, so it is not offered then.
            picture_adjustments=frozenset(PICTURE_RANGES)
            - (frozenset({"gamma"}) if self._options.hardware_decoding else frozenset()),
            supports_aspect_ratio=True,
            supports_crop=True,
            supports_zoom=True,
            rotation="restart",
            supports_equalizer=True,
            equalizer_presets=self._eq_presets,
            equalizer_bands_hz=self._eq_bands,
            supports_frame_step=True,
            supports_frame_back_step=False,  # libVLC 3 can only step forward
            supports_snapshot=True,
            network_schemes=STREAM_SCHEMES,
            supports_chapters=True,
            subtitle_style="restart",  # style is an instance option: a new engine applies it
            max_delay_ms=60_000,
            hardware_decoding="requested" if self._options.hardware_decoding else "disabled",
            notes=(
                "Hardware decoder in use is read from the libVLC log.",
                "Subtitle style applies to plain-text subtitles; ASS/SSA keep their own styling.",
                "Brightness and contrast look stronger with software decoding than with hardware "
                "decoding (different libVLC filters).",
                "Rotation and flips restart playback at the same position.",
                "Web streams are fetched by Babarify's own loopback proxy (http/https redirects only).",
            ),
        )

    def diagnostics(self) -> Mapping[str, str]:
        return {
            "engine": f"libVLC {self._version}",
            "decoder": self._decoder_status(),
            "hwdec": self._hwdec or "none reported (software decoding or not yet decoding)",
            "video_output": self._vout or "unknown",
            "log_errors": str(sum(1 for line in self._log if line.startswith("4 "))),
        }

    def recent_log(self) -> list[str]:
        return list(self._log)

    def _decoder_status(self) -> str:
        """Report only what libVLC confirmed: hardware needs its log line, software needs decoded frames."""
        info = self.get_media_info()
        if info is not None and info.video_codec is None and info.audio_codec is not None:
            return "no video"
        if self._hwdec:
            return f"hardware ({self._hwdec.split(' (')[0]})"
        if self.playback_stats().get("decoded_video", 0) > 0:
            return "software"
        return "not decoding yet"

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
        # Let the host (Qt) receive mouse and keyboard input over the video, e.g. double-click
        # for fullscreen. Must be set before the video output is created.
        self._player.video_set_mouse_input(False)
        self._player.video_set_key_input(False)

    def _do_open(self, uri: str, autoplay: bool) -> None:
        self._stop_requested = False
        self._hwdec = None
        self._info_pending = True
        self._confirmed = False
        self._loading_target = None
        self._pending_seek = None
        self._cancel_open_timer()
        self._open_generation += 1  # a pending timeout belongs to the previous media
        self._playlist_depth = 0
        self._open_location(uri)

    def _open_location(self, uri: str) -> None:
        """Load ``uri`` (validated) into the player and start it; network addresses get the open
        timeout, and http/https go through the stream proxy."""
        old = self._media
        if is_network_uri(uri):
            location = get_proxy().wrap(uri) if uri_scheme(uri) in ("http", "https") else uri
            self._media = self._instance.media_new_location(location)
            self._start_open_timer()
        else:
            self._media = self._instance.media_new_path(uri)
        # Must be a per-media option: libVLC 3.0.24 silently ignores --avcodec-hw at instance level
        # (M4 finding: "Off" kept using D3D11VA until this was moved here).
        self._media.add_option(f":avcodec-hw={'any' if self._options.hardware_decoding else 'none'}")
        effect = AUDIO_EFFECTS.get(self._options.audio_effect, "")
        if effect:
            self._media.add_option(f":audio-filter={effect}")
        self._player.set_media(self._media)
        self._apply_picture()
        self._apply_equalizer()
        if old is not None:
            old.release()
        if self._player.play() != 0:
            self._fail(PlaybackError(ErrorCode.MEDIA_OPEN_FAILED, self._last_error()))

    def _start_open_timer(self) -> None:
        self._cancel_open_timer()
        self._open_generation += 1
        self._open_started = time.monotonic()
        timer = threading.Timer(OPEN_TIMEOUT_S, self._on_open_timeout, args=(self._open_generation,))
        timer.daemon = True
        self._open_timer = timer
        timer.start()

    def _cancel_open_timer(self) -> None:
        if self._open_timer is not None:
            self._open_timer.cancel()
            self._open_timer = None

    def _on_open_timeout(self, generation: int) -> None:
        if generation == self._open_generation and self.state is S.LOADING:
            self._defer(self._give_up_opening, generation)

    def _give_up_opening(self, generation: int) -> None:
        if generation != self._open_generation or self.state is not S.LOADING or self._player is None:
            return
        self._player.stop()  # not a user stop: the Stopped event is ignored
        self._fail(PlaybackError(ErrorCode.NETWORK_ERROR, f"nothing played within {OPEN_TIMEOUT_S:.0f} s"))

    def _network_error(self, fallback: str) -> PlaybackError:
        proxy = get_proxy()
        reasons = proxy.failures_since(self._open_started) if self._open_started else []
        if reasons:
            return PlaybackError(ErrorCode.NETWORK_ERROR, reasons[-1])
        removed = proxy.removed_since(self._open_started) if self._open_started else 0
        if removed:
            fallback = f"{removed} playlist entries were removed because they are not web addresses"
        return PlaybackError(ErrorCode.NETWORK_ERROR, fallback)

    def _do_play(self) -> None:
        state = self.state
        if state is S.PAUSED:
            self._player.set_pause(0)
        elif state is S.ENDED:
            self._restart()

    def _restart(self) -> None:
        # An ended libVLC 3 player ignores play(); it must be stopped first. The automatic
        # "Stopped" event is ignored because no stop was requested by the user.
        self._info_pending = True
        self._player.stop()
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
            # libVLC cannot seek an ended player: restart it, then seek and pause on "Playing".
            self._pending_seek = position_ms
            self._restart()
            return
        self._player.set_time(position_ms)
        # libVLC sends no TimeChanged while paused, including when a pause was requested a moment
        # earlier and has not taken effect yet (M4 seek-storm finding). Report the accepted target;
        # while playing, the next TimeChanged supersedes it.
        self._set_position(position_ms)

    # ---------------------------------------------- audio and subtitles
    def _refetch(self) -> None:
        """Re-seek to the current position so the demuxer re-reads data it already dropped
        (M5 spike: without it a newly selected subtitle track or a new delay misses lines
        that were read ahead)."""
        if self.state in (S.PLAYING, S.PAUSED, S.BUFFERING):
            self._player.set_time(self._player.get_time())

    def _do_select_audio(self, track_id: int) -> None:
        self._player.audio_set_track(track_id)
        self._defer(self._collect_media_info)

    def _do_select_subtitle(self, track_id: int | None) -> None:
        self._player.video_set_spu(-1 if track_id is None else track_id)
        if track_id is not None:
            self._refetch()
        self._defer(self._collect_media_info)

    def _do_add_subtitle(self, path: str) -> None:
        before = {tid for tid, _ in (self._player.video_get_spu_description() or [])}
        uri = Path(path).as_uri()
        if self._player.add_slave(self._vlc.MediaSlaveType.subtitle, uri, True) != 0:
            self._notice(ErrorCode.MEDIA_OPEN_FAILED, f"could not load subtitle file {Path(path).name}")
            return
        self._defer(self._confirm_subtitle, path, before)

    def _confirm_subtitle(self, path: str, before: set[int]) -> None:
        """libVLC reports success even for unreadable files (M5 spike): confirm a track appeared."""
        deadline = time.monotonic() + EXTERNAL_SUBTITLE_TIMEOUT_S
        while time.monotonic() < deadline and self._player is not None:
            now = {tid for tid, _ in (self._player.video_get_spu_description() or [])}
            added = sorted(now - before - {-1})
            if added:
                if self._player.video_get_spu() not in added:
                    self._player.video_set_spu(added[0])
                self._refetch()
                self._collect_media_info()
                return
            time.sleep(0.1)
        if self._player is not None:
            self._notice(ErrorCode.MEDIA_OPEN_FAILED, f"could not read subtitle file {Path(path).name}")

    def _do_set_audio_delay(self, delay_ms: int) -> None:
        self._player.audio_set_delay(delay_ms * 1000)

    def _do_set_subtitle_delay(self, delay_ms: int) -> None:
        self._player.video_set_spu_delay(delay_ms * 1000)
        self._refetch()  # subtitles already queued would otherwise keep their old timing

    # ---------------------------------------------- picture and sound (M7)
    def _do_set_picture(self, picture: PictureSettings) -> None:
        self._picture = picture
        self._apply_picture()

    def _apply_picture(self) -> None:
        """R30: values changed while the adjust filter is on are applied unreliably (hardware
        decoding shows wrong colours, software decoding ignores them). Always switch the filter
        off, set every value, then switch it on again."""
        player, picture = self._player, self._picture
        if player is None:
            return
        adjust = self._vlc.VideoAdjustOption
        player.video_set_adjust_int(adjust.Enable, 0)
        if picture.is_default:
            return
        for option, value in (
            (adjust.Brightness, picture.brightness),
            (adjust.Contrast, picture.contrast),
            (adjust.Saturation, picture.saturation),
            (adjust.Hue, picture.hue),
            (adjust.Gamma, picture.gamma),
        ):
            player.video_set_adjust_float(option, value)
        player.video_set_adjust_int(adjust.Enable, 1)

    def _do_set_video_geometry(self, aspect: str, crop: str, zoom: float) -> None:
        self._geometry = (aspect, crop, zoom)
        self._apply_geometry()

    def _apply_geometry(self) -> None:
        if self._player is None:
            return
        aspect, crop, zoom = self._geometry
        self._player.video_set_aspect_ratio(aspect_to_engine(aspect))
        self._player.video_set_crop_geometry(aspect_to_engine(crop))
        self._player.video_set_scale(zoom)

    def _do_set_equalizer(self, equalizer: EqualizerSettings) -> None:
        self._equalizer = equalizer
        self._apply_equalizer()

    def _apply_equalizer(self) -> None:
        if self._player is None:
            return
        eq = self._equalizer
        if not eq.enabled:
            self._player.set_equalizer(None)
            return
        settings = self._vlc.AudioEqualizer()
        settings.set_preamp(eq.preamp_db)
        for index, value in enumerate(eq.bands_db):
            settings.set_amp_at_index(value, index)
        self._player.set_equalizer(settings)  # libVLC copies the values; the object can go
        settings.release()

    def equalizer_preset(self, name: str) -> EqualizerSettings:
        if name not in self._eq_presets:
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, f"no equalizer preset {name!r}")
        handle = self._vlc.libvlc_audio_equalizer_new_from_preset(self._eq_presets.index(name))
        try:
            preamp = self._vlc.libvlc_audio_equalizer_get_preamp(handle)
            bands = tuple(
                self._vlc.libvlc_audio_equalizer_get_amp_at_index(handle, i)
                for i in range(len(self._eq_bands))
            )
        finally:
            self._vlc.libvlc_audio_equalizer_release(handle)
        return EqualizerSettings(True, name, round(preamp, 1), tuple(round(b, 1) for b in bands)).normalized()

    def _do_frame_step(self, backward: bool) -> None:
        self._player.next_frame()

    def _do_take_snapshot(self, path: str) -> None:
        if self._player.video_take_snapshot(0, path, 0, 0) != 0:
            self._notice(ErrorCode.ENGINE_FAILURE, "the snapshot could not be saved")

    def _do_set_volume(self, level: int) -> None:
        self._player.audio_set_volume(level)

    def _do_set_muted(self, enabled: bool) -> None:
        self._player.audio_set_mute(enabled)

    def _do_set_rate(self, rate: float) -> None:
        self._player.set_rate(rate)

    def _do_close(self) -> None:
        self._cancel_open_timer()
        try:
            # Stop receiving log lines first; the shared instance itself stays alive (R20).
            if self._shared is not None:
                self._shared.remove_sink(self._on_log_line)
            if self._player is not None:
                self._stop_requested = True
                self._player.stop()
                self._player.release()
            if self._media is not None:
                self._media.release()
        finally:
            self._player = self._media = self._instance = None
            self._shared = None

    # ------------------------------------------------- libVLC callbacks
    # These run on libVLC threads: update state only, defer player calls.
    def _on_es_added(self, _event: Any) -> None:
        # Some demuxers (MPEG-TS/PS, Ogg) announce streams, and their video size, only after
        # Playing: refresh media info when streams are added and when the video output appears.
        if self._info_pending or self._info_refresh_queued:
            return
        self._info_refresh_queued = True
        self._defer(self._refresh_media_info)

    def _refresh_media_info(self) -> None:
        self._info_refresh_queued = False
        self._collect_media_info()

    def _on_playing(self, _event: Any) -> None:
        if self._info_pending:
            self._info_pending = False
            self._defer(self._collect_media_info)
        state = self.state
        if state is S.ENDED and self._pending_seek is not None:
            target, self._pending_seek = self._pending_seek, None
            self._defer(self._seek_and_pause, target)  # Paused event moves us ENDED -> PAUSED
            return
        if state is S.LOADING:
            if not self._autoplay:
                self._defer(self._player.set_pause, 1)  # Paused event sets the target
                return
            self._loading_target = S.PLAYING
            self._enter_target_if_confirmed()
            return
        self._transition(S.PLAYING)

    def _on_paused(self, _event: Any) -> None:
        if self.state is S.LOADING:
            self._loading_target = S.PAUSED
            self._enter_target_if_confirmed()
            return
        self._transition(S.PAUSED)

    def _confirm_media(self) -> None:
        self._cancel_open_timer()
        if not self._confirmed:
            self._confirmed = True
            self._enter_target_if_confirmed()

    def _enter_target_if_confirmed(self) -> None:
        if self._confirmed and self._loading_target is not None and self.state is S.LOADING:
            target, self._loading_target = self._loading_target, None
            self._transition(target)

    def _seek_and_pause(self, position_ms: int) -> None:
        self._player.set_time(position_ms)
        self._player.set_pause(1)
        self._set_position(position_ms)

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
            if self.state is S.LOADING and self._open_playlist_entry():
                return
            if self._uri is not None and is_network_uri(self._uri):
                self._fail(self._network_error("the address did not return playable media"))
            else:
                self._fail(PlaybackError(ErrorCode.MEDIA_OPEN_FAILED, self._last_error()))
        else:
            self._end_reached()

    def _open_playlist_entry(self) -> bool:
        """A playlist ends at once and lists its entries as sub-items (M8 spike). Play the first
        web or rtsp entry; file:, vlc: and every other scheme are skipped. Returns False when
        there is nothing to play (the caller reports the failure)."""
        media = self._media
        items = media.subitems() if media is not None else None
        if items is None:
            return False
        try:
            mrls = [items.item_at_index(i).get_mrl() or "" for i in range(min(items.count(), 1000))]
        finally:
            items.release()
        if not mrls:
            return False
        if self._playlist_depth >= MAX_PLAYLIST_DEPTH:
            self._fail(PlaybackError(ErrorCode.UNSUPPORTED, "playlists nested too deeply"))
            return True
        proxy = get_proxy()
        skipped, target = 0, None
        for mrl in mrls:
            candidate = proxy.unwrap(mrl) or mrl
            try:
                target = validate_stream_url(candidate)
                break
            except PlaybackError:
                skipped += 1
        skipped += proxy.removed_since(self._open_started) if self._open_started else 0
        if target is None:
            self._fail(
                PlaybackError(
                    ErrorCode.UNSUPPORTED, f"the playlist has no web or rtsp entries ({skipped} skipped)"
                )
            )
            return True
        if skipped:
            self._notice(
                ErrorCode.UNSUPPORTED, f"skipped {skipped} playlist entries that are not web addresses"
            )
        self._playlist_depth += 1
        self._confirmed = False
        self._open_location(target)
        return True

    def _on_error(self, _event: Any) -> None:
        if self._uri is not None and is_network_uri(self._uri):
            self._cancel_open_timer()
            self._fail(self._network_error(self._last_error()))
            return
        code = ErrorCode.MEDIA_OPEN_FAILED if self.state is S.LOADING else ErrorCode.ENGINE_FAILURE
        self._fail(PlaybackError(code, self._last_error()))

    def _on_time(self, event: Any) -> None:
        self._set_position(event.u.new_time)
        if event.u.new_time > 0:
            self._confirm_media()
        # Video size can arrive after every event that announces it (MPEG-TS/PS, Ogg):
        # retry media info a few times while playback progresses.
        if self._size_retries and not self._info_refresh_queued:
            now = time.monotonic()
            if now - self._last_size_retry >= 0.5:
                self._last_size_retry = now
                self._size_retries -= 1
                self._info_refresh_queued = True
                self._defer(self._refresh_media_info)

    def _on_length(self, event: Any) -> None:
        self._set_duration(event.u.new_length)
        if event.u.new_length > 0:
            self._confirm_media()

    def _on_vout(self, event: Any) -> None:
        if event.u.new_count > 0:
            self._confirm_media()
        self._on_es_added(event)

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
        return errors[-1][2:] if errors else "libVLC reported an error"  # strip the log-level prefix

    def _read_metadata(self, media: Any) -> tuple[tuple[str, str], ...]:
        meta = self._vlc.Meta
        file_name = Path(self._uri).name if self._uri and not is_network_uri(self._uri) else ""
        out = []
        for name, label in _META_FIELDS:
            value = media.get_meta(getattr(meta, name))
            if isinstance(value, bytes):
                value = value.decode("utf-8", "replace")
            value = " ".join(str(value or "").split())[:500]
            # libVLC reports the file name (or the address) as the title of untagged media.
            if value and not (name == "Title" and value in (file_name, self._uri, Path(file_name).stem)):
                out.append((label, value))
        return tuple(out)

    def _read_tracks(self) -> list[_Track]:
        return read_media_tracks(self._vlc, self._media)

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
                    id=t.id,
                    kind=kinds[t.type],
                    title=names.get(t.id),
                    language=t.language,
                    codec=t.codec,
                    width=t.width,
                    height=t.height,
                    frame_rate=t.fps,
                    channels=t.channels,
                    sample_rate=t.rate,
                    bitrate=t.bitrate,
                    selected=(
                        kinds[t.type] is TrackKind.VIDEO
                        or (kinds[t.type] is TrackKind.AUDIO and t.id == audio_sel)
                        or (kinds[t.type] is TrackKind.SUBTITLE and t.id == spu_sel)
                    ),
                )
                for t in raw
                if t.type in kinds
            )
            # Tracks added at runtime (external subtitle files) exist only on the player.
            known = {t.id for t in tracks}
            for kind, descriptions, current in (
                (TrackKind.AUDIO, player.audio_get_track_description() or [], audio_sel),
                (TrackKind.SUBTITLE, player.video_get_spu_description() or [], spu_sel),
            ):
                for tid, desc in descriptions:
                    if tid >= 0 and tid not in known:
                        title = (desc or b"").decode("utf-8", "replace")
                        tracks = (*tracks, TrackInfo(tid, kind, title=title, selected=tid == current))
            # The video output may not exist yet (e.g. MPEG-TS/PS, Ogg): fall back to stream info.
            raw_video = next((t for t in raw if t.type == 1), None)
            width, height = player.video_get_size(0) or (0, 0)
            if not width and raw_video:
                width, height = raw_video.width, raw_video.height
            video = next((t for t in tracks if t.kind is TrackKind.VIDEO), None)
            audio = next((t for t in tracks if t.kind is TrackKind.AUDIO), None)
            self._set_media_info(
                MediaInfo(
                    uri=self._uri or "",
                    duration_ms=player.get_length() or None,
                    video_codec=video.codec if video else None,
                    width=width or None,
                    height=height or None,
                    frame_rate=player.get_fps() or (raw_video.fps if raw_video else 0.0) or None,
                    audio_codec=audio.codec if audio else None,
                    tracks=tracks,
                    chapters=read_chapters(self._vlc, player),
                    metadata=self._read_metadata(media),
                )
            )
            self._size_retries = 6 if (video is not None and not width) else 0
        except Exception as exc:  # diagnostics must never break playback
            self._log.append(f"4 babarify: media info failed: {exc!r}")
