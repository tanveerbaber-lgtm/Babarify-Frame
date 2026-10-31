"""Application-layer playback controller.

Owns the active engine, keeps listener and video-output wiring across engine
switches, and guarantees clean shutdown. Later milestones add resume,
history and playlists here rather than in the UI.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import PlaybackEvent
from babarify_frame.core.models import (
    EngineCapabilities,
    EngineOptions,
    MediaInfo,
    PlaybackState,
    PlaybackStatus,
    SubtitleStyle,
)
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import EngineFactory

log = logging.getLogger(__name__)


class PlaybackController:
    def __init__(self, factory: EngineFactory) -> None:
        self._factory = factory
        self._engine: PlaybackEngine | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._listeners: list[Callable[[PlaybackEvent], None]] = []
        self._window_id: int | None = None

    @property
    def engine(self) -> PlaybackEngine:
        if self._engine is None:
            raise PlaybackError(ErrorCode.INVALID_STATE, "no playback engine is active")
        return self._engine

    @property
    def engine_name(self) -> str | None:
        return self._engine.name if self._engine else None

    def start(self, engine_name: str, options: EngineOptions | None = None) -> None:
        """Create (or switch to) an engine. The previous engine is closed first."""
        self.attach(self._factory.create(engine_name, options))

    def attach(self, engine: PlaybackEngine) -> None:
        """Adopt an already-initialised engine (e.g. created on a worker thread)."""
        self.shutdown()
        self._unsubscribe = engine.subscribe(self._dispatch)
        if self._window_id is not None:
            engine.set_video_output(self._window_id)
        self._engine = engine

    def add_listener(self, listener: Callable[[PlaybackEvent], None]) -> None:
        self._listeners.append(listener)

    def set_video_output(self, window_id: int | None) -> None:
        self._window_id = window_id
        if self._engine is not None:
            self._engine.set_video_output(window_id)

    # Commands --------------------------------------------------------
    def open(self, uri: str, *, autoplay: bool = True) -> None:
        self.engine.open_media(uri, autoplay=autoplay)

    def toggle_play_pause(self) -> None:
        if self.engine.get_playback_state().state in (PlaybackState.PLAYING, PlaybackState.BUFFERING):
            self.engine.pause()
        else:
            self.engine.play()

    def play(self) -> None:
        self.engine.play()

    def pause(self) -> None:
        self.engine.pause()

    def stop(self) -> None:
        self.engine.stop()

    def seek(self, position_ms: int) -> None:
        self.engine.seek(position_ms)

    def set_volume(self, level: int) -> None:
        self.engine.set_volume(level)

    def set_muted(self, enabled: bool) -> None:
        self.engine.set_muted(enabled)

    def set_playback_rate(self, rate: float) -> None:
        self.engine.set_playback_rate(rate)

    def select_audio_track(self, track_id: int) -> None:
        self.engine.select_audio_track(track_id)

    def select_subtitle_track(self, track_id: int | None) -> None:
        self.engine.select_subtitle_track(track_id)

    def add_subtitle_file(self, path: str) -> None:
        self.engine.add_subtitle_file(path)

    def set_audio_delay(self, delay_ms: int) -> None:
        self.engine.set_audio_delay(delay_ms)

    def set_subtitle_delay(self, delay_ms: int) -> None:
        self.engine.set_subtitle_delay(delay_ms)

    def set_subtitle_style(self, style: SubtitleStyle) -> None:
        self.engine.set_subtitle_style(style)

    # Queries ---------------------------------------------------------
    def status(self) -> PlaybackStatus:
        return self.engine.get_playback_state()

    def media_info(self) -> MediaInfo | None:
        return self.engine.get_media_info()

    def capabilities(self) -> EngineCapabilities:
        return self.engine.get_capabilities()

    # Lifecycle -------------------------------------------------------
    def shutdown(self) -> None:
        """Close the active engine. Never raises; safe to call repeatedly."""
        engine, self._engine = self._engine, None
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if engine is not None:
            try:
                engine.close()
            except Exception:
                log.exception("error while shutting down engine %s", engine.name)

    def _dispatch(self, event: PlaybackEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                log.exception("controller listener failed")
