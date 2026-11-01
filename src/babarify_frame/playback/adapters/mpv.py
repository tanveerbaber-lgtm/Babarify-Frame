"""mpv adapter — M1 evaluation prototype.

Uses python-mpv against ``libmpv-2.dll`` found by ``_engine_paths``.

Findings encoded here (see docs/milestones/M1/benchmark-report.md):
* python-mpv event objects point into mpv-owned memory and are only valid
  inside the callback; read everything immediately.
* User config, Lua scripts and youtube-dl/yt-dlp are disabled so playback is
  reproducible and media URLs can never launch external programs.
* ``wid`` (host window) must be set before the first video output is created.
"""

from __future__ import annotations

import contextlib
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from babarify_frame.core.enhancements import PICTURE_RANGES, PictureSettings, VideoTransform, aspect_to_engine
from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.models import (
    EngineCapabilities,
    EngineOptions,
    MediaInfo,
    PlaybackState,
    SubtitlePosition,
    SubtitleStyle,
    TrackInfo,
    TrackKind,
)
from babarify_frame.playback.adapters._engine_paths import add_dll_dir, find_mpv_dir
from babarify_frame.playback.contracts import EngineBase
from babarify_frame.playback.factory import EngineProbe

S = PlaybackState
_END_FILE = 7
_FILE_LOADED = 8
_END_REASON_ERROR = 4
_KINDS = {"video": TrackKind.VIDEO, "audio": TrackKind.AUDIO, "sub": TrackKind.SUBTITLE}
# Named subtitle positions -> mpv sub-pos (percent of window height; 100 = bottom).
_SUB_POS = {
    SubtitlePosition.BOTTOM: 100,
    SubtitlePosition.SLIGHTLY_RAISED: 95,
    SubtitlePosition.RAISED: 85,
    SubtitlePosition.HIGH: 70,
}
_MPV_DEFAULT_SUB_FONT_SIZE = 55


def _load_mpv() -> Any:
    mpv_dir = find_mpv_dir()
    if mpv_dir is None:
        raise PlaybackError(
            ErrorCode.ENGINE_UNAVAILABLE, "libmpv-2.dll not found (.engines/mpv or BABARIFY_MPV_DIR)"
        )
    add_dll_dir(mpv_dir)
    import mpv

    return mpv


def probe() -> EngineProbe:
    try:
        mpv = _load_mpv()
    except PlaybackError as exc:
        return EngineProbe("mpv", False, detail=exc.detail)
    except OSError as exc:
        return EngineProbe("mpv", False, detail=str(exc))
    # The release version is only available from a live handle.
    player = mpv.MPV(vo="null", ao="null", config=False, load_scripts=False, ytdl=False)
    try:
        release = str(player.mpv_version).removeprefix("mpv ")
    finally:
        player.terminate()
    return EngineProbe("mpv", True, release, str(find_mpv_dir()))


class MpvEngine(EngineBase):
    name = "mpv"

    def __init__(
        self, options: EngineOptions | None = None, extra_options: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__()
        self._options = options or EngineOptions()
        self._extra = dict(extra_options or {})
        self._player: Any = None
        self._log: deque[str] = deque(maxlen=300)
        self._version = ""
        self._window_id: int | None = None
        self._last_error = ""
        self._paused = False  # mirrored from the "pause" observer; callbacks never query mpv

    # ------------------------------------------------------------ setup
    def _do_initialize(self) -> None:
        mpv = _load_mpv()
        options: dict[str, Any] = {
            "config": False,
            "load_scripts": False,
            "ytdl": False,
            "osc": False,
            "input_default_bindings": False,
            "input_vo_keyboard": False,
            "keep_open": "yes",
            "idle": "yes",
            "hwdec": "auto-safe" if self._options.hardware_decoding else "no",
            "force_window": "no",
            **self._extra,
        }
        self._player = mpv.MPV(log_handler=self._on_log, loglevel="info", **options)
        self._version = str(self._player.mpv_version).removeprefix("mpv ")
        self._player.register_event_callback(self._on_event)
        for name, handler in (
            ("time-pos", self._on_time),
            ("duration", self._on_duration),
            ("pause", self._on_pause),
            ("paused-for-cache", self._on_cache),
            ("eof-reached", self._on_eof),
        ):
            self._player.observe_property(name, handler)
        self._apply_style(self._options.subtitle_style)

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            engine_name="mpv",
            engine_version=self._version,
            min_rate=0.25,
            max_rate=4.0,
            max_volume=130,  # mpv default volume-max
            supports_audio_tracks=True,
            supports_subtitle_tracks=True,
            supports_embedding=True,
            supports_external_subtitles=True,
            picture_adjustments=frozenset(PICTURE_RANGES),
            supports_aspect_ratio=True,
            supports_crop=False,  # not offered: mpv's video-crop needs a newer build than the one tested
            supports_zoom=False,  # mpv's video-zoom is relative, not "fit" / "actual pixels"
            rotation="live",
            supports_equalizer=False,  # would need an lavfi filter chain; not offered
            supports_frame_step=True,
            supports_frame_back_step=True,
            supports_snapshot=True,
            supports_dual_subtitles=False,  # mpv can (secondary-sid); not offered until verified
            subtitle_style="live",
            max_delay_ms=60_000,
            hardware_decoding="requested" if self._options.hardware_decoding else "disabled",
            notes=(
                "Host window must be set before the first file is opened.",
                "Subtitle style applies to plain-text subtitles; ASS/SSA keep their own styling.",
            ),
        )

    def diagnostics(self) -> Mapping[str, str]:
        player = self._player
        if player is None:
            return {"engine": f"mpv {self._version}"}
        hwdec = str(self._prop("hwdec-current") or "")
        info = self.get_media_info()
        if info is None:
            decoder = "not decoding yet"
        elif info.video_codec is None:
            decoder = "no video"
        else:
            decoder = f"hardware ({hwdec})" if hwdec not in ("", "no") else "software"
        return {
            "engine": f"mpv {self._version}",
            "decoder": decoder,
            "hwdec": hwdec or "none",
            "video_output": str(self._prop("current-vo") or "unknown"),
            "log_errors": str(sum(1 for line in self._log if line.startswith("error"))),
        }

    def recent_log(self) -> list[str]:
        return list(self._log)

    def playback_stats(self) -> dict[str, int]:
        """Frame counters for the current media (cumulative since open)."""
        vo_drops = self._prop("frame-drop-count")
        decoder_drops = self._prop("decoder-frame-drop-count")
        if vo_drops is None and decoder_drops is None:
            return {}
        return {
            "dropped": int(vo_drops or 0) + int(decoder_drops or 0),
            "dropped_vo": int(vo_drops or 0),
            "dropped_decoder": int(decoder_drops or 0),
        }

    # ---------------------------------------------------------- commands
    def _do_set_video_output(self, window_id: int | None) -> None:
        self._window_id = window_id
        self._player["wid"] = str(window_id) if window_id else "-1"
        if window_id:
            self._player["force-window"] = "no"

    def _do_open(self, uri: str, autoplay: bool) -> None:
        self._last_error = ""
        self._paused = not autoplay
        self._player.pause = not autoplay
        self._player.command("loadfile", uri, "replace")

    def _do_play(self) -> None:
        state = self.state
        if state is S.ENDED:
            self._player.command("seek", 0, "absolute")
        if state is not S.LOADING:
            self._player.pause = False

    def _do_pause(self) -> None:
        if self.state is not S.LOADING:
            self._player.pause = True

    def _do_stop(self) -> None:
        self._player.command("stop")
        self._set_position(0)
        self._transition(S.READY)

    def _do_seek(self, position_ms: int) -> None:
        self._player.command("seek", position_ms / 1000.0, "absolute")

    def _do_set_volume(self, level: int) -> None:
        self._player.volume = level

    def _do_set_muted(self, enabled: bool) -> None:
        self._player.mute = enabled

    def _do_set_rate(self, rate: float) -> None:
        self._player.speed = rate

    # ---------------------------------------------- audio and subtitles
    def _do_select_audio(self, track_id: int) -> None:
        self._player["aid"] = track_id
        self._defer(self._collect_media_info)

    def _do_select_subtitle(self, track_id: int | None) -> None:
        self._player["sid"] = "no" if track_id is None else track_id
        self._defer(self._collect_media_info)

    def _do_add_subtitle(self, path: str) -> None:
        try:
            self._player.command("sub-add", path, "select")
        except SystemError as exc:  # python-mpv raises this when the command fails
            self._notice(ErrorCode.MEDIA_OPEN_FAILED, f"could not read subtitle file {Path(path).name}")
            self._log.append(f"error babarify: sub-add failed: {exc!r}")
            return
        self._defer(self._collect_media_info)

    def _do_set_audio_delay(self, delay_ms: int) -> None:
        self._player["audio-delay"] = delay_ms / 1000.0

    def _do_set_subtitle_delay(self, delay_ms: int) -> None:
        self._player["sub-delay"] = delay_ms / 1000.0

    def _do_set_subtitle_style(self, style: SubtitleStyle) -> None:
        self._apply_style(style)

    def _apply_style(self, style: SubtitleStyle) -> None:
        style = style.normalized()
        player = self._player
        player["sub-font-size"] = round(_MPV_DEFAULT_SUB_FONT_SIZE * style.size_pct / 100)
        player["sub-color"] = style.text_color
        alpha = round(style.background_opacity * 255 / 100)
        player["sub-back-color"] = f"#{alpha:02X}000000"
        # mpv >= 0.38; older builds draw sub-back-color only with an opaque box
        with contextlib.suppress(AttributeError, RuntimeError, TypeError):
            player["sub-border-style"] = "background-box" if alpha else "outline-and-shadow"
        player["sub-pos"] = _SUB_POS[style.position]
        if style.font_family:
            player["sub-font"] = style.font_family

    # ---------------------------------------------- picture and sound (M7)
    def _do_set_picture(self, picture: PictureSettings) -> None:
        # mpv uses -100..100 around 0 = unchanged for each property.
        def scaled(value: float) -> int:
            return max(-100, min(100, round(value)))

        player = self._player
        player["brightness"] = scaled((picture.brightness - 1.0) * 100)
        player["contrast"] = scaled((picture.contrast - 1.0) * 100)
        player["saturation"] = scaled((picture.saturation - 1.0) * 100)  # 3.0 is capped at 2x
        player["hue"] = scaled(picture.hue / 180 * 100)
        player["gamma"] = scaled((picture.gamma - 1.0) * 100)

    def _do_set_video_geometry(self, aspect: str, crop: str, zoom: float) -> None:
        self._player["video-aspect-override"] = aspect_to_engine(aspect) or "-1"

    def _do_set_rotation(self, transform: VideoTransform) -> None:
        player = self._player
        degrees = {
            VideoTransform.ROTATE_90: 90,
            VideoTransform.ROTATE_180: 180,
            VideoTransform.ROTATE_270: 270,
        }
        player["video-rotate"] = degrees.get(transform, 0)
        flip = {VideoTransform.FLIP_HORIZONTAL: "hflip", VideoTransform.FLIP_VERTICAL: "vflip"}.get(transform)
        player.command("vf", "set", flip or "")

    def _do_frame_step(self, backward: bool) -> None:
        self._player.command("frame-back-step" if backward else "frame-step")

    def _do_take_snapshot(self, path: str) -> None:
        try:
            self._player.command("screenshot-to-file", path, "video")
        except SystemError:
            self._notice(ErrorCode.ENGINE_FAILURE, "the snapshot could not be saved")

    def _do_close(self) -> None:
        try:
            if self._player is not None:
                self._player.terminate()
        finally:
            self._player = None

    # ---------------------------------------------------- mpv callbacks
    # These run on python-mpv's event thread.
    def _on_log(self, level: str, prefix: str, text: str) -> None:
        line = f"{level} {prefix}: {text.rstrip()}"
        self._log.append(line)
        if level in ("error", "fatal"):
            self._last_error = line

    def _on_event(self, event: Any) -> None:
        eid = event.event_id.value
        if eid == _FILE_LOADED:
            self._defer(self._collect_media_info)
            if self.state is S.LOADING:
                self._transition(S.PAUSED if self._paused else S.PLAYING)
        elif eid == _END_FILE:
            data = event.data
            if data is not None and data.reason == _END_REASON_ERROR:
                code = ErrorCode.MEDIA_OPEN_FAILED if self.state is S.LOADING else ErrorCode.ENGINE_FAILURE
                self._fail(PlaybackError(code, self._last_error or f"mpv end-file error {data.error}"))

    def _on_time(self, _name: str, value: Any) -> None:
        if value is not None and self.state not in (S.LOADING, S.READY):
            self._set_position(round(float(value) * 1000))

    def _on_duration(self, _name: str, value: Any) -> None:
        self._set_duration(round(float(value) * 1000) if value else None)

    def _on_pause(self, _name: str, paused: Any) -> None:
        self._paused = bool(paused)
        state = self.state
        if state in (S.PLAYING, S.BUFFERING) and paused:
            self._transition(S.PAUSED)
        elif state in (S.PAUSED, S.ENDED) and paused is False:
            self._transition(S.PLAYING)

    def _on_cache(self, _name: str, waiting: Any) -> None:
        state = self.state
        if waiting and state is S.PLAYING:
            self._transition(S.BUFFERING)
        elif not waiting and state is S.BUFFERING:
            self._transition(S.PLAYING)

    def _on_eof(self, _name: str, reached: Any) -> None:
        if reached and self.state in (S.PLAYING, S.PAUSED, S.BUFFERING):
            self._end_reached()
        elif reached is False and self.state is S.ENDED:
            self._transition(S.PAUSED if self._paused else S.PLAYING)

    # ------------------------------------------------------------ helpers
    def _prop(self, name: str) -> Any:
        try:
            player = self._player
            if player is None or player.handle is None:
                return None
            return player._get_property(name)
        except (AttributeError, RuntimeError):
            return None

    def _collect_media_info(self) -> None:
        try:
            track_list = self._prop("track-list") or []
            tracks = tuple(
                TrackInfo(
                    id=int(t["id"]),
                    kind=_KINDS[t["type"]],
                    title=t.get("title"),
                    language=t.get("lang"),
                    codec=t.get("codec"),
                    selected=bool(t.get("selected")),
                )
                for t in track_list
                if t.get("type") in _KINDS
            )
            params = self._prop("video-params") or {}
            video = next((t for t in tracks if t.kind is TrackKind.VIDEO and t.selected), None)
            audio = next((t for t in tracks if t.kind is TrackKind.AUDIO and t.selected), None)
            duration = self._prop("duration")
            self._set_media_info(
                MediaInfo(
                    uri=self._uri or "",
                    duration_ms=round(float(duration) * 1000) if duration else None,
                    video_codec=video.codec if video else None,
                    width=params.get("w"),
                    height=params.get("h"),
                    frame_rate=self._prop("container-fps"),
                    audio_codec=audio.codec if audio else None,
                    tracks=tracks,
                )
            )
        except Exception as exc:
            self._log.append(f"error babarify: media info failed: {exc!r}")
