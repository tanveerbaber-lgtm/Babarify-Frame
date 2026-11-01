"""Deterministic in-memory engine for tests and UI development.

It never decodes media. Time only moves when ``advance()`` is called.

Mock URIs: ``mock://<name>?duration=<ms>&fail=open&chapters=<n>`` (all parameters optional;
``chapters`` splits the duration into n equal chapters, ``duration=0`` is a live stream).
Existing local files are also accepted and get ``default_duration_ms``. http/https/rtsp
addresses are simulated streams (M8): the host ``fail.invalid`` gives a network error, and
the query takes the same parameters as mock URIs; without ``duration`` a stream is live.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from babarify_frame.core.enhancements import (
    PICTURE_RANGES,
    EqualizerSettings,
    PictureSettings,
    VideoTransform,
)
from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.models import (
    Chapter,
    EngineCapabilities,
    EngineOptions,
    MediaInfo,
    PlaybackState,
    SubtitleStyle,
    TrackInfo,
    TrackKind,
)
from babarify_frame.core.network import STREAM_SCHEMES, is_network_uri
from babarify_frame.playback.contracts import EngineBase

S = PlaybackState

# A valid 1x1 PNG, so snapshot handling can be tested without a renderer.
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


class MockEngine(EngineBase):
    name = "mock"
    allowed_schemes = frozenset({"mock", "file"}) | STREAM_SCHEMES

    def __init__(
        self,
        options: EngineOptions | None = None,
        *,
        auto_complete_loading: bool = True,
        default_duration_ms: int = 60_000,
    ) -> None:
        super().__init__()
        self.options = options or EngineOptions()
        self.subtitle_style = self.options.subtitle_style
        self.picture = PictureSettings()
        self.geometry: tuple[str, str, float] = ("", "", 0.0)
        self.equalizer = EqualizerSettings()
        self.transform = self.options.video_transform
        self.auto_complete_loading = auto_complete_loading
        self.default_duration_ms = default_duration_ms
        self.window_id: int | None = None
        self.calls: list[str] = []
        self.closed_resources = False
        self._pending: MediaInfo | None = None

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            engine_name="mock",
            engine_version="1",
            max_volume=150,
            supports_audio_tracks=True,
            supports_subtitle_tracks=True,
            supports_embedding=True,
            supports_external_subtitles=True,
            subtitle_style="live",
            picture_adjustments=frozenset(PICTURE_RANGES),
            supports_aspect_ratio=True,
            supports_crop=True,
            supports_zoom=True,
            rotation="live",
            supports_equalizer=True,
            equalizer_presets=("Flat", "Rock", "Classical"),
            equalizer_bands_hz=(31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000),
            supports_frame_step=True,
            supports_frame_back_step=False,
            supports_snapshot=True,
            network_schemes=STREAM_SCHEMES,
            supports_chapters=True,
            hardware_decoding="unavailable",
            notes=("Simulated engine: no real decoding.",),
        )

    def diagnostics(self) -> Mapping[str, str]:
        decoder = "software (simulated)" if self.get_media_info() is not None else "not decoding yet"
        return {"engine": "mock", "decoder": decoder, "hwdec": "none"}

    # ------------------------------------------------------------ hooks
    def _do_initialize(self) -> None:
        self.calls.append("initialize")

    def _do_set_video_output(self, window_id: int | None) -> None:
        self.window_id = window_id

    def _do_open(self, uri: str, autoplay: bool) -> None:
        self.calls.append(f"open:{uri}")
        parts = urlsplit(uri)
        network = is_network_uri(uri)
        params = parse_qs(parts.query) if parts.scheme == "mock" or network else {}
        if network and parts.hostname == "fail.invalid":
            self._fail(
                PlaybackError(ErrorCode.NETWORK_ERROR, "the server name fail.invalid could not be found")
            )
            return
        if params.get("fail") == ["open"]:
            self._fail(PlaybackError(ErrorCode.MEDIA_OPEN_FAILED, f"simulated open failure: {uri}"))
            return
        default = 0 if network else self.default_duration_ms
        duration = int(params.get("duration", [default])[0])
        count = int(params.get("chapters", ["0"])[0])
        chapters = (
            tuple(Chapter(i, duration * i // count, f"Part {i + 1}") for i in range(count))
            if count > 0 and duration > 0
            else ()
        )
        self._pending = MediaInfo(
            uri=uri,
            duration_ms=duration or None,
            chapters=chapters,
            metadata=(("Title", "Mock title"), ("Artist", "Mock artist")),
            video_codec="h264",
            width=1920,
            height=1080,
            frame_rate=30.0,
            audio_codec="aac",
            tracks=(
                TrackInfo(
                    1, TrackKind.VIDEO, codec="h264", selected=True, width=1920, height=1080, frame_rate=30.0
                ),
                TrackInfo(
                    2,
                    TrackKind.AUDIO,
                    title="English",
                    language="eng",
                    codec="aac",
                    selected=True,
                    channels=2,
                    sample_rate=48000,
                ),
                TrackInfo(3, TrackKind.AUDIO, title="French", language="fra", codec="ac3"),
                TrackInfo(4, TrackKind.SUBTITLE, title="English", language="eng", codec="subrip"),
                TrackInfo(5, TrackKind.SUBTITLE, title="French", language="fra", codec="ass"),
            ),
        )
        if self.auto_complete_loading:
            self.complete_loading()

    def _do_play(self) -> None:
        self.calls.append("play")
        state = self.state
        if state is S.LOADING:
            return  # autoplay flag already updated by EngineBase
        if state is S.ENDED:
            self._set_position(0)
        self._transition(S.PLAYING)

    def _do_pause(self) -> None:
        self.calls.append("pause")
        if self.state is not S.LOADING:
            self._transition(S.PAUSED)

    def _do_stop(self) -> None:
        self.calls.append("stop")
        self._set_position(0)
        self._transition(S.READY)

    def _do_seek(self, position_ms: int) -> None:
        self.calls.append(f"seek:{position_ms}")
        self._set_position(position_ms)
        if self.state is S.ENDED:
            self._transition(S.PAUSED)

    def _do_set_volume(self, level: int) -> None:
        self.calls.append(f"volume:{level}")

    def _do_set_muted(self, enabled: bool) -> None:
        self.calls.append(f"muted:{enabled}")

    def _do_set_rate(self, rate: float) -> None:
        self.calls.append(f"rate:{rate}")

    def _do_close(self) -> None:
        self.calls.append("close")
        self.closed_resources = True

    # ---------------------------------------------- audio and subtitles
    def _reselect(self, kind: TrackKind, track_id: int | None) -> None:
        info = self.get_media_info()
        if info is None:
            return
        tracks = tuple(replace(t, selected=(t.id == track_id)) if t.kind is kind else t for t in info.tracks)
        self._set_media_info(replace(info, tracks=tracks))

    def _do_select_audio(self, track_id: int) -> None:
        self.calls.append(f"audio:{track_id}")
        self._reselect(TrackKind.AUDIO, track_id)

    def _do_select_subtitle(self, track_id: int | None) -> None:
        self.calls.append(f"subtitle:{track_id}")
        self._reselect(TrackKind.SUBTITLE, track_id)

    def _do_add_subtitle(self, path: str) -> None:
        self.calls.append(f"add_subtitle:{path}")
        info = self.get_media_info()
        if info is None:
            return
        if "broken" in Path(path).name:
            self._notice(ErrorCode.MEDIA_OPEN_FAILED, f"could not read subtitle file {Path(path).name}")
            return
        new_id = max(t.id for t in info.tracks) + 1
        added = TrackInfo(new_id, TrackKind.SUBTITLE, title=Path(path).name, codec="subrip")
        self._set_media_info(replace(info, tracks=(*info.tracks, added)))
        self._reselect(TrackKind.SUBTITLE, new_id)

    def _do_set_audio_delay(self, delay_ms: int) -> None:
        self.calls.append(f"audio_delay:{delay_ms}")

    def _do_set_subtitle_delay(self, delay_ms: int) -> None:
        self.calls.append(f"subtitle_delay:{delay_ms}")

    def _do_set_subtitle_style(self, style: SubtitleStyle) -> None:
        self.calls.append(f"style:{style.text_color}:{style.size_pct}")
        self.subtitle_style = style

    # ---------------------------------------------- picture and sound (M7)
    def _do_set_picture(self, picture: PictureSettings) -> None:
        self.calls.append("picture")
        self.picture = picture

    def _do_set_video_geometry(self, aspect: str, crop: str, zoom: float) -> None:
        self.calls.append(f"geometry:{aspect}:{crop}:{zoom}")
        self.geometry = (aspect, crop, zoom)

    def _do_set_equalizer(self, equalizer: EqualizerSettings) -> None:
        self.calls.append(f"equalizer:{equalizer.enabled}")
        self.equalizer = equalizer

    def _do_set_rotation(self, transform: VideoTransform) -> None:
        self.calls.append(f"rotation:{transform.value}")
        self.transform = transform

    def equalizer_preset(self, name: str) -> EqualizerSettings:
        if name not in self.get_capabilities().equalizer_presets:
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, f"no equalizer preset {name!r}")
        level = {"Flat": 0.0, "Rock": 4.0, "Classical": -2.0}[name]
        return EqualizerSettings(True, name, 0.0, (level,) * 10)

    def _do_frame_step(self, backward: bool) -> None:
        self.calls.append("frame_step")
        self._set_position(self.get_playback_state().position_ms + 40)  # 25 fps

    def _do_take_snapshot(self, path: str) -> None:
        self.calls.append(f"snapshot:{path}")
        Path(path).write_bytes(_TINY_PNG)

    # ---------------------------------------------- simulation controls
    def complete_loading(self) -> None:
        """Finish a pending open, as a real engine would after demuxing."""
        if self.state is not S.LOADING or self._pending is None:
            raise PlaybackError(ErrorCode.INVALID_STATE, "nothing is loading")
        self._set_media_info(self._pending)
        self._transition(S.PLAYING if self._autoplay else S.PAUSED)

    def advance(self, ms: int) -> None:
        """Move the simulated clock forward while playing."""
        if self.state is not S.PLAYING:
            return
        status = self.get_playback_state()
        position = status.position_ms + round(ms * status.rate)
        duration = status.duration_ms
        if duration is not None and position >= duration:
            self._set_position(duration)
            self._end_reached()
        else:
            self._set_position(position)

    def simulate_buffering(self, active: bool) -> None:
        self._transition(S.BUFFERING if active else S.PLAYING)

    def simulate_error(self, code: ErrorCode = ErrorCode.ENGINE_FAILURE, detail: str = "simulated") -> None:
        self._fail(PlaybackError(code, detail))
