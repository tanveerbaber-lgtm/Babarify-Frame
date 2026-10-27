"""The common playback contract and a base class that enforces it.

The UI and application layers depend only on ``PlaybackEngine``. Adapters
subclass ``EngineBase`` and implement the ``_do_*`` hooks; validation, state
rules and event delivery live here so every engine behaves the same way.

Threading: public methods may be called from one controlling thread (the UI
thread). Adapters report engine activity from any thread through the
``_transition``/``_emit`` helpers; listeners are therefore invoked on
arbitrary threads and must marshal to the UI thread themselves. The internal
lock is never held while calling into an engine or a listener.
"""

from __future__ import annotations

import contextlib
import logging
import math
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import (
    EndReached,
    ErrorOccurred,
    MediaInfoChanged,
    PlaybackEvent,
    PositionChanged,
    StateChanged,
)
from babarify_frame.core.models import EngineCapabilities, MediaInfo, PlaybackState, PlaybackStatus
from babarify_frame.playback.lifecycle import can_transition, command_allowed

log = logging.getLogger(__name__)

Listener = Callable[[PlaybackEvent], None]


class PlaybackEngine(ABC):
    """Engine-independent playback operations used by the rest of the application."""

    name: str

    @abstractmethod
    def initialize(self) -> None: ...
    @abstractmethod
    def set_video_output(self, window_id: int | None) -> None: ...
    @abstractmethod
    def open_media(self, uri: str, *, autoplay: bool = True) -> None: ...
    @abstractmethod
    def play(self) -> None: ...
    @abstractmethod
    def pause(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def seek(self, position_ms: int) -> None: ...
    @abstractmethod
    def set_volume(self, level: int) -> None: ...
    @abstractmethod
    def set_muted(self, enabled: bool) -> None: ...
    @abstractmethod
    def set_playback_rate(self, rate: float) -> None: ...
    @abstractmethod
    def get_playback_state(self) -> PlaybackStatus: ...
    @abstractmethod
    def get_media_info(self) -> MediaInfo | None: ...
    @abstractmethod
    def get_capabilities(self) -> EngineCapabilities: ...
    @abstractmethod
    def subscribe(self, listener: Listener) -> Callable[[], None]: ...
    @abstractmethod
    def diagnostics(self) -> Mapping[str, str]:
        """Human-readable diagnostics. Standard keys: "engine", "decoder" ("hardware (<api>)",
        "software", "not decoding yet" or "no video"), "video_output", "log_errors"."""

    @abstractmethod
    def close(self) -> None: ...

    def playback_stats(self) -> Mapping[str, int]:
        """Frame counters for the current media (e.g. "displayed", "dropped"); empty if unknown."""
        return {}

    def recent_log(self) -> list[str]:
        """Most recent engine log lines, oldest first; empty if the engine has no log."""
        return []


def normalize_local_uri(uri: str, allowed_schemes: frozenset[str]) -> str:
    """Validate a media URI and return a canonical form.

    Plain paths and ``file:`` URIs must point at an existing file. Network
    schemes are rejected until network playback is designed (M8).
    """
    if not isinstance(uri, str) or not uri.strip():
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "media URI must be a non-empty string")
    if any(ord(c) < 32 for c in uri):
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "media URI contains control characters")

    parts = urlsplit(uri)
    # A single letter "scheme" is a Windows drive (C:\...), not a URI scheme.
    scheme = parts.scheme.lower() if len(parts.scheme) > 1 else ""
    if scheme and scheme != "file":
        if scheme not in allowed_schemes:
            raise PlaybackError(ErrorCode.UNSUPPORTED, f"URI scheme '{scheme}' is not supported")
        return uri

    if "file" not in allowed_schemes:
        raise PlaybackError(ErrorCode.UNSUPPORTED, "local files are not supported by this engine")
    if scheme == "file":
        from urllib.request import url2pathname

        path = Path(url2pathname(parts.path if not parts.netloc else f"//{parts.netloc}{parts.path}"))
    else:
        path = Path(uri)
    path = path.expanduser().resolve()
    if not path.is_file():
        raise PlaybackError(ErrorCode.MEDIA_NOT_FOUND, str(path))
    return str(path)


class EngineBase(PlaybackEngine):
    """Shared validation, lifecycle enforcement and event delivery."""

    allowed_schemes: frozenset[str] = frozenset({"file"})

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = PlaybackState.UNINITIALIZED
        self._listeners: list[Listener] = []
        self._uri: str | None = None
        self._autoplay = True
        self._position_ms = 0
        self._duration_ms: int | None = None
        self._volume = 100
        self._muted = False
        self._rate = 1.0
        self._media_info: MediaInfo | None = None
        self.rejected_transitions: list[tuple[PlaybackState, PlaybackState]] = []
        self._worker: ThreadPoolExecutor | None = None
        self._closing = False

    # ------------------------------------------------------------ hooks
    @abstractmethod
    def _do_initialize(self) -> None: ...
    @abstractmethod
    def _do_open(self, uri: str, autoplay: bool) -> None: ...
    @abstractmethod
    def _do_play(self) -> None: ...
    @abstractmethod
    def _do_pause(self) -> None: ...
    @abstractmethod
    def _do_stop(self) -> None: ...
    @abstractmethod
    def _do_seek(self, position_ms: int) -> None: ...
    @abstractmethod
    def _do_set_volume(self, level: int) -> None: ...
    @abstractmethod
    def _do_set_muted(self, enabled: bool) -> None: ...
    @abstractmethod
    def _do_set_rate(self, rate: float) -> None: ...
    @abstractmethod
    def _do_close(self) -> None: ...

    def _do_set_video_output(self, window_id: int | None) -> None:
        raise PlaybackError(ErrorCode.UNSUPPORTED, f"{self.name} cannot render into a host window")

    # ------------------------------------------------------- public API
    def initialize(self) -> None:
        with self._lock:
            if self._state is not PlaybackState.UNINITIALIZED:
                raise PlaybackError(ErrorCode.INVALID_STATE, f"cannot initialise from {self._state.value}")
        try:
            self._do_initialize()
        except PlaybackError:
            raise
        except Exception as exc:  # engine library missing or broken
            raise PlaybackError(ErrorCode.ENGINE_UNAVAILABLE, f"{type(exc).__name__}: {exc}") from exc
        self._transition(PlaybackState.READY)

    def set_video_output(self, window_id: int | None) -> None:
        self._require_open_engine()
        if window_id is not None and (not isinstance(window_id, int) or window_id <= 0):
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "window id must be a positive integer")
        self._do_set_video_output(window_id)

    def open_media(self, uri: str, *, autoplay: bool = True) -> None:
        self._require("open_media")
        canonical = normalize_local_uri(uri, self.allowed_schemes)
        with self._lock:
            self._uri = canonical
            self._autoplay = autoplay
            self._position_ms = 0
            self._duration_ms = None
            self._media_info = None
        self._transition(PlaybackState.LOADING)
        self._do_open(canonical, autoplay)

    def play(self) -> None:
        state = self._require("play")
        if state is PlaybackState.READY:
            # After stop() the media stays selected; playing again reloads it.
            with self._lock:
                uri = self._uri
                self._autoplay = True
            if uri is None:
                raise PlaybackError(ErrorCode.INVALID_STATE, "no media is open")
            self._transition(PlaybackState.LOADING)
            self._do_open(uri, True)
            return
        if state is PlaybackState.LOADING:
            with self._lock:
                self._autoplay = True
        self._do_play()

    def pause(self) -> None:
        state = self._require("pause")
        if state is PlaybackState.LOADING:
            with self._lock:
                self._autoplay = False
        self._do_pause()

    def stop(self) -> None:
        self._require("stop")
        self._do_stop()

    def seek(self, position_ms: int) -> None:
        self._require("seek")
        if not self.get_capabilities().can_seek:
            raise PlaybackError(ErrorCode.UNSUPPORTED, "seeking is not supported")
        if isinstance(position_ms, bool) or not isinstance(position_ms, int) or position_ms < 0:
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "position must be a non-negative integer (ms)")
        duration = self._duration_ms
        if duration is not None and position_ms > duration:
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, f"position {position_ms} ms is past the end")
        self._do_seek(position_ms)

    def set_volume(self, level: int) -> None:
        self._require("set_volume")
        max_volume = self.get_capabilities().max_volume
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= max_volume:
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, f"volume must be an integer 0..{max_volume}")
        self._do_set_volume(level)
        with self._lock:
            self._volume = level

    def set_muted(self, enabled: bool) -> None:
        self._require("set_muted")
        self._do_set_muted(bool(enabled))
        with self._lock:
            self._muted = bool(enabled)

    def set_playback_rate(self, rate: float) -> None:
        self._require("set_playback_rate")
        caps = self.get_capabilities()
        if not caps.can_change_rate:
            raise PlaybackError(ErrorCode.UNSUPPORTED, "playback rate cannot be changed")
        if isinstance(rate, bool) or not isinstance(rate, int | float) or not math.isfinite(rate):
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "rate must be a finite number")
        if not caps.min_rate <= rate <= caps.max_rate:
            raise PlaybackError(ErrorCode.INVALID_ARGUMENT, f"rate must be {caps.min_rate}..{caps.max_rate}")
        self._do_set_rate(float(rate))
        with self._lock:
            self._rate = float(rate)

    def get_playback_state(self) -> PlaybackStatus:
        with self._lock:
            return PlaybackStatus(
                state=self._state,
                position_ms=self._position_ms,
                duration_ms=self._duration_ms,
                volume=self._volume,
                muted=self._muted,
                rate=self._rate,
                uri=self._uri,
            )

    @property
    def state(self) -> PlaybackState:
        with self._lock:
            return self._state

    def get_media_info(self) -> MediaInfo | None:
        with self._lock:
            return self._media_info

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def diagnostics(self) -> Mapping[str, str]:
        return {}

    def close(self) -> None:
        """Release engine resources. Safe to call more than once and after errors."""
        with self._lock:
            if self._state is PlaybackState.CLOSED or self._closing:
                return
            self._closing = True
            worker, self._worker = self._worker, None
        # Drain deferred engine calls first: they must never run against a released engine.
        if worker is not None:
            worker.shutdown(wait=True, cancel_futures=True)
        try:
            self._do_close()
        except Exception:
            log.exception("%s: error while closing engine", self.name)
        finally:
            self._transition(PlaybackState.CLOSED)
            with self._lock:
                self._listeners.clear()

    # ------------------------------------------------- adapter helpers
    def _defer(self, fn: Callable[..., object], *args: object) -> None:
        """Run ``fn`` on this engine's worker thread.

        Engine callbacks use this instead of calling back into the engine
        synchronously (which can deadlock). Ignored once ``close()`` has begun.
        """
        with self._lock:
            if self._closing or self._state is PlaybackState.CLOSED:
                return
            if self._worker is None:
                self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{self.name}-cmd")
            worker = self._worker
        with contextlib.suppress(RuntimeError):  # worker shut down between the check and submit
            worker.submit(self._run_deferred, fn, args)

    def _run_deferred(self, fn: Callable[..., object], args: tuple[object, ...]) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("%s: deferred engine call failed", self.name)

    def worker_idle(self, timeout: float = 2.0) -> bool:
        """Wait until deferred calls queued so far have run (tests and benchmark)."""
        done = threading.Event()
        self._defer(done.set)
        with self._lock:
            idle = self._worker is None
        return idle or done.wait(timeout)

    def _require(self, command: str) -> PlaybackState:
        with self._lock:
            state = self._state
        if not command_allowed(command, state):
            raise PlaybackError(ErrorCode.INVALID_STATE, f"'{command}' is not allowed while {state.value}")
        return state

    def _require_open_engine(self) -> None:
        with self._lock:
            if self._state in (PlaybackState.UNINITIALIZED, PlaybackState.CLOSED):
                raise PlaybackError(ErrorCode.INVALID_STATE, f"engine is {self._state.value}")

    def _transition(self, new: PlaybackState) -> bool:
        """Move to ``new`` if allowed. Returns False (and records it) if rejected."""
        with self._lock:
            old = self._state
            if old is new:
                return True
            if not can_transition(old, new):
                self.rejected_transitions.append((old, new))
                log.warning("%s: rejected state transition %s -> %s", self.name, old.value, new.value)
                return False
            self._state = new
        self._emit(StateChanged(old, new))
        return True

    def _set_position(self, position_ms: int) -> None:
        with self._lock:
            if self._state is PlaybackState.CLOSED:
                return
            self._position_ms = max(0, int(position_ms))
            position = self._position_ms
        self._emit(PositionChanged(position))

    def _set_duration(self, duration_ms: int | None) -> None:
        with self._lock:
            self._duration_ms = duration_ms if duration_ms and duration_ms > 0 else None

    def _set_media_info(self, info: MediaInfo) -> None:
        with self._lock:
            self._media_info = info
            if info.duration_ms:
                self._duration_ms = info.duration_ms
        self._emit(MediaInfoChanged(info))

    def _end_reached(self) -> None:
        with self._lock:
            uri = self._uri or ""
        if self._transition(PlaybackState.ENDED):
            self._emit(EndReached(uri))

    def _fail(self, error: PlaybackError) -> None:
        if self._transition(PlaybackState.ERROR):
            self._emit(ErrorOccurred(error))

    def _emit(self, event: PlaybackEvent) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                log.exception("%s: playback listener failed", self.name)
