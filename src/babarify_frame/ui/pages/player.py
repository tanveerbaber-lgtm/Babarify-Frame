"""Now Playing page: video surface, state messages and the control bar, wired to the controller.

Engine events arrive on engine threads and are marshalled through ``UiBridge``. Position is
polled (``POSITION_REFRESH_MS``) rather than pushed. The engine is created on a worker
thread and must be shut down (``shutdown()``) while the window still exists.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.configuration.preferences import Preferences
from babarify_frame.core.errors import PlaybackError
from babarify_frame.core.events import ErrorOccurred, MediaInfoChanged, StateChanged
from babarify_frame.core.models import EngineOptions, MediaInfo, PlaybackState
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.controller import PlaybackController
from babarify_frame.playback.factory import EngineFactory
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.controls import ControlBar
from babarify_frame.ui.widgets import VideoSurface, glyph_icon

S = PlaybackState
POSITION_REFRESH_MS = 100
STATUS_REFRESH_TICKS = 10  # refresh engine diagnostics about once a second
CURSOR_POLL_MS = 200
VOLUME_STEP = 5
HAS_MEDIA = frozenset({S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED})
SEEKABLE = frozenset({S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED})


class PlayerPage(QWidget):
    status_changed = Signal(str)
    title_changed = Signal(str)  # media name, "" when nothing is open
    state_changed = Signal(object)  # PlaybackState
    engine_ready = Signal(bool)
    video_started = Signal()  # first frame of a video (not audio-only) after open
    open_requested = Signal()
    fullscreen_requested = Signal()

    def __init__(
        self, factory: EngineFactory, engine_name: str, prefs: Preferences, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._factory = factory
        self._engine_name = engine_name
        self._prefs = prefs
        self._controller = PlaybackController(factory)
        self._events = UiBridge(self)
        self._events.delivered.connect(self._on_engine_event)
        self._controller.add_listener(self._events.post)
        self._engine_bridge = UiBridge(self)
        self._engine_bridge.delivered.connect(self._on_engine_created)
        self._engine_thread: threading.Thread | None = None
        self._pending_open: str | None = None
        self._resume: tuple[str, int, bool] | None = None  # (uri, position, playing) across restarts
        self._resume_position: int | None = None
        self.last_error = ""  # most recent playback error, for the Playback info panel
        self._media_name = ""
        self._state = S.UNINITIALIZED
        self._duration_ms: int | None = None
        self._is_audio_only = False
        self._video_announced = False
        self._closing = False
        self._ticks = 0
        self._fullscreen = False
        self._last_cursor = QPoint()
        self._idle_ms = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_stage(), stretch=1)
        self.controls = ControlBar()
        layout.addWidget(self.controls)
        self._connect_controls()
        self.controls.set_volume(prefs.volume)
        self.controls.set_muted(prefs.muted)
        self.controls.set_title("")

        self._position_timer = QTimer(self)
        self._position_timer.setInterval(POSITION_REFRESH_MS)
        self._position_timer.timeout.connect(self._refresh_position)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(CURSOR_POLL_MS)
        self._cursor_timer.timeout.connect(self._poll_cursor)
        self._show_message("info", "Starting playback engine…", "")
        self._apply_state(S.UNINITIALIZED)

    # ------------------------------------------------------------ layout
    def _build_stage(self) -> QStackedWidget:
        self._stage = QStackedWidget()
        page = QFrame()
        page.setObjectName("messagePage")
        box = QVBoxLayout(page)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setSpacing(theme.M)
        self._message_icon = QLabel()
        self._message_title = QLabel()
        self._message_title.setObjectName("title")
        self._message_body = QLabel()
        self._message_body.setObjectName("muted")
        for label in (self._message_icon, self._message_title, self._message_body):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            box.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._message_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._message_body.setMaximumWidth(640)
        self._message_action = QPushButton("Open another file…")
        self._message_action.setAccessibleName("Open another file")
        self._message_action.clicked.connect(self.open_requested)
        box.addSpacing(theme.S)
        box.addWidget(self._message_action, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.video = VideoSurface()
        self.video.double_clicked.connect(self.fullscreen_requested)
        self._stage.addWidget(page)
        self._stage.addWidget(self.video)
        return self._stage

    def _connect_controls(self) -> None:
        c = self.controls
        c.play_clicked.connect(self.toggle_play_pause)
        c.stop_clicked.connect(self.stop)
        c.back_clicked.connect(lambda: self.seek_step(-1))
        c.forward_clicked.connect(lambda: self.seek_step(1))
        c.seek_requested.connect(self.seek_to)
        c.volume_changed.connect(self.set_volume)
        c.mute_clicked.connect(self.toggle_mute)
        c.rate_selected.connect(self.set_rate)
        c.fullscreen_clicked.connect(self.fullscreen_requested)

    # ----------------------------------------------------------- engine
    @property
    def controller(self) -> PlaybackController:
        return self._controller

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def engine_is_ready(self) -> bool:
        return self._controller.engine_name is not None

    @property
    def has_media(self) -> bool:
        return self._state in HAS_MEDIA or (self._state is S.READY and bool(self._media_name))

    @property
    def is_seekable(self) -> bool:
        return self.engine_is_ready and self._state in SEEKABLE and bool(self._duration_ms)

    def start_engine(self) -> None:
        """Create the engine on a worker thread; the UI stays responsive while the DLL loads."""
        self._controller.set_video_output(int(self.video.winId()))

        options = EngineOptions(hardware_decoding=self._prefs.hardware_decoding)

        def work() -> None:
            try:
                self._engine_bridge.post(self._factory.create(self._engine_name, options))
            except PlaybackError as exc:
                self._engine_bridge.post(exc)

        self._engine_thread = threading.Thread(target=work, name="engine-start", daemon=True)
        self._engine_thread.start()

    def _on_engine_created(self, result: object) -> None:
        if isinstance(result, PlaybackError):
            self._show_message(
                "error", "Playback engine unavailable", f"{result.user_message}\n{result.detail}"
            )
            self._message_action.hide()
            self._apply_state(S.UNINITIALIZED)
            self.engine_ready.emit(False)
            return
        if not isinstance(result, PlaybackEngine):
            return
        if self._closing:
            result.close()  # the window closed while the engine was starting
            return
        self._controller.attach(result)
        self._run(lambda: self._controller.set_volume(self._prefs.volume))
        self._run(lambda: self._controller.set_muted(self._prefs.muted))
        self.status_changed.emit(result.diagnostics().get("engine", result.name))
        self._show_message("info", "Nothing is playing", "Open a file from Home, or press Ctrl+O.")
        self._apply_state(S.READY)
        self._position_timer.start()
        self.engine_ready.emit(True)
        if self._resume is not None:
            uri, position, playing = self._resume
            self._resume_position = position
            self._resume = None
            self.open_path(uri, autoplay=playing)
        elif self._pending_open:
            path, self._pending_open = self._pending_open, None
            self.open_path(path)

    # --------------------------------------------------------- commands
    def restart_engine(self) -> None:
        """Recreate the engine (e.g. after changing hardware decoding) and resume the current file."""
        status = self._controller.status() if self.engine_is_ready else None
        if status is not None and status.uri and self.has_media and self._state is not S.ERROR:
            self._resume = (status.uri, status.position_ms, status.state in (S.PLAYING, S.BUFFERING))
        self._position_timer.stop()
        self._controller.shutdown()  # the video surface stays alive: close-before-window holds
        if self._engine_thread is not None:
            self._engine_thread.join(timeout=10)
        self._apply_state(S.UNINITIALIZED)
        self._show_message("info", "Restarting playback engine…", "")
        self.start_engine()  # actions update through state_changed; engine_ready(False) means failure

    def open_path(self, path: str, *, autoplay: bool = True) -> None:
        if not self.engine_is_ready:
            self._pending_open = path  # opened once the engine is ready
            return
        self._media_name = Path(path).name if "://" not in path else path
        self._duration_ms = None
        self._is_audio_only = False
        self._video_announced = False
        self.controls.reset_position()
        self.controls.set_title(self._media_name)
        self.controls.set_rate(1.0)
        # Update first: an engine may report failure while open() is still running, and the
        # (queued) error event must win over these defaults.
        self.title_changed.emit(self._media_name)
        self._stage.setCurrentWidget(self.video)
        try:
            self._controller.open(path, autoplay=autoplay)
        except PlaybackError as exc:
            self._show_error(exc)

    def toggle_play_pause(self) -> None:
        if self.has_media and self._state is not S.ERROR:
            self._run(self._controller.toggle_play_pause)

    def stop(self) -> None:
        if self._state in HAS_MEDIA or self._state is S.ERROR:
            self._run(self._controller.stop)

    def seek_to(self, position_ms: int) -> None:
        if self._state in SEEKABLE:
            target = max(0, min(position_ms, self._duration_ms or position_ms))
            self._run(lambda: self._controller.seek(target))
            self._refresh_position()

    def seek_step(self, direction: int) -> None:
        if self._state in SEEKABLE:
            step = self._prefs.seek_step_s * 1000
            self.seek_to(self._controller.status().position_ms + direction * step)

    def set_volume(self, level: int) -> None:
        self.controls.set_volume(level)
        if self.engine_is_ready:
            self._run(lambda: self._controller.set_volume(level))
            if level > 0 and self._controller.status().muted:
                self.toggle_mute()

    def step_volume(self, delta: int) -> None:
        self.set_volume(max(0, min(100, self.controls.volume.value() + delta)))

    def toggle_mute(self) -> None:
        if not self.engine_is_ready:
            return
        muted = not self._controller.status().muted
        self._run(lambda: self._controller.set_muted(muted))
        self.controls.set_muted(self._controller.status().muted)

    def set_rate(self, rate: float) -> None:
        if self.engine_is_ready:
            self._run(lambda: self._controller.set_playback_rate(rate))
            self.controls.set_rate(self._controller.status().rate)

    def volume_state(self) -> tuple[int, bool]:
        if self.engine_is_ready:
            status = self._controller.status()
            return min(100, status.volume), status.muted
        return self.controls.volume.value(), self._prefs.muted

    def set_preferences(self, prefs: Preferences) -> None:
        restart = prefs.hardware_decoding != self._prefs.hardware_decoding and self.engine_is_ready
        self._prefs = prefs
        if restart:
            self.restart_engine()

    def _run(self, command: Callable[[], object]) -> None:
        """Run a controller command; report refused commands instead of raising into Qt."""
        try:
            command()
        except PlaybackError as exc:
            self.status_changed.emit(exc.user_message)

    # ------------------------------------------------- fullscreen chrome
    def set_fullscreen_mode(self, fullscreen: bool) -> None:
        self._fullscreen = fullscreen
        self.controls.set_fullscreen(fullscreen)
        self._show_controls()
        if fullscreen:
            self._last_cursor = QCursor.pos()
            self._cursor_timer.start()
        else:
            self._cursor_timer.stop()

    def _poll_cursor(self) -> None:
        """Auto-hide controls in fullscreen while playing; any mouse movement brings them back.

        Polling the cursor position works even when the engine's native video window
        receives the mouse events instead of Qt.
        """
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            self._show_controls()
            return
        self._idle_ms += CURSOR_POLL_MS
        if (
            self._idle_ms >= self._prefs.controls_hide_delay_ms
            and self._state is S.PLAYING
            and not self.controls.seek.user_dragging
        ):
            self._hide_controls()

    def _show_controls(self) -> None:
        self._idle_ms = 0
        self.controls.show()
        self.unsetCursor()

    def _hide_controls(self) -> None:
        if self.controls.isVisible():
            self.controls.hide()
            self.setCursor(Qt.CursorShape.BlankCursor)

    @property
    def controls_hidden(self) -> bool:
        return not self.controls.isVisible()

    # ------------------------------------------------------- engine events
    def _on_engine_event(self, event: object) -> None:
        if isinstance(event, StateChanged):
            self._apply_state(event.new)
        elif isinstance(event, MediaInfoChanged):
            self._apply_media_info(event.info)
        elif isinstance(event, ErrorOccurred):
            self._show_error(event.error)

    def _apply_state(self, state: PlaybackState) -> None:
        self._state = state
        ready = self.engine_is_ready
        self.controls.set_enabled_controls(
            play=ready and self.has_media and state is not S.ERROR,
            stop=ready and (state in HAS_MEDIA or state is S.ERROR),
            seek=self.is_seekable,
        )
        self.controls.set_playing(state in (S.PLAYING, S.BUFFERING))
        status = {
            S.LOADING: f"Opening {self._media_name}…",
            S.BUFFERING: "Buffering…",
            S.PAUSED: "Paused",
            S.ENDED: "Ended",
        }.get(state)
        if status:
            self.status_changed.emit(status)
        elif state is S.PLAYING:
            self._show_engine_status()
            if not self._is_audio_only and not self._video_announced:
                info = self._controller.media_info()
                if info is not None and info.video_codec:
                    self._video_announced = True
                    self.video_started.emit()
        if self._resume_position is not None and state in (S.PLAYING, S.PAUSED):
            position, self._resume_position = self._resume_position, None
            if position > 0:
                self._run(lambda: self._controller.seek(position))
        if state is S.READY and self._media_name:
            self._show_message("info", self._media_name, "Stopped. Press Space to play again.")
            self.controls.set_position(0, self._duration_ms)
        if state is not S.PLAYING:
            self._show_controls()
        self.state_changed.emit(state)

    def _apply_media_info(self, info: MediaInfo) -> None:
        self._duration_ms = info.duration_ms
        self.controls.set_position(self._controller.status().position_ms, info.duration_ms)
        if info.video_codec is None and info.audio_codec is not None:
            self._is_audio_only = True
            self._show_message("music", self._media_name, f"Audio · {info.audio_codec}")
            self._message_action.hide()
        elif self._state in (S.PLAYING, S.PAUSED, S.BUFFERING, S.LOADING):
            self._stage.setCurrentWidget(self.video)
        self._apply_state(self._state)

    def _show_engine_status(self) -> None:
        if not self.engine_is_ready:
            return
        info = self._controller.media_info()
        diag = self._controller.engine.diagnostics()
        parts = [diag.get("engine", "")]
        if info and info.video_codec:
            parts.append(f"{info.video_codec} {info.width}x{info.height}")
            parts.append(f"decoder: {diag.get('decoder', 'unknown')}")
        if info and info.audio_codec:
            parts.append(info.audio_codec)
        self.status_changed.emit(" · ".join(p for p in parts if p))

    def _show_error(self, error: PlaybackError) -> None:
        self.last_error = f"{error.code.value}: {error.detail}" if error.detail else error.code.value
        detail = f"{self._media_name}\n{error.detail}" if self._media_name else error.detail
        self._show_message("error", error.user_message, detail)
        self.status_changed.emit(error.user_message)
        self.title_changed.emit("")

    def _show_message(self, glyph: str, title: str, body: str) -> None:
        color = {"error": theme.RED, "music": theme.CYAN}.get(glyph, theme.TEXT_MUTED)
        icon = glyph_icon(glyph, color, theme.TEXT_DISABLED, size=64)
        self._message_icon.setVisible(icon is not None)
        if icon is not None:
            self._message_icon.setPixmap(icon.pixmap(QSize(48, 48)))
        self._message_title.setText(title)
        self._message_body.setText(body)
        self._message_body.setVisible(bool(body))
        self._message_action.setVisible(glyph == "error" and self.engine_is_ready)
        self._stage.setCurrentIndex(0)

    @property
    def message(self) -> tuple[str, str]:
        return self._message_title.text(), self._message_body.text()

    def _refresh_position(self) -> None:
        if not self.engine_is_ready or self._state not in HAS_MEDIA:
            return
        status = self._controller.status()
        if status.duration_ms and status.duration_ms != self._duration_ms:
            self._duration_ms = status.duration_ms
            self._apply_state(self._state)
        self.controls.set_position(status.position_ms, self._duration_ms)
        self._ticks += 1
        if status.state is S.PLAYING and self._ticks % STATUS_REFRESH_TICKS == 0:
            self._show_engine_status()

    # --------------------------------------------------------- lifecycle
    def shutdown(self) -> None:
        """Close the engine. Must run while the window (and the video surface) still exists."""
        self._closing = True
        self._position_timer.stop()
        self._cursor_timer.stop()
        self._controller.shutdown()
        if self._engine_thread is not None:
            self._engine_thread.join(timeout=10)
