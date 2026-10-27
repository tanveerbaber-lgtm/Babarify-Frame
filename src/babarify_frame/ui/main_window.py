"""Main player window (M2): video surface, transport controls, fullscreen, honest state display.

The window talks only to ``PlaybackController``. Engine events arrive on engine threads and
are marshalled to the UI thread through ``UiBridge``. The engine is created on a worker
thread so start-up never blocks the UI, and it is always shut down before the window is
destroyed (see docs/architecture/overview.md, "close the engine before its host window").
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSlider,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame import BRAND, PRODUCT_NAME, TAGLINE, __version__
from babarify_frame.core.errors import PlaybackError
from babarify_frame.core.events import ErrorOccurred, MediaInfoChanged, StateChanged
from babarify_frame.core.models import MediaInfo, PlaybackState
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.controller import PlaybackController
from babarify_frame.playback.factory import EngineFactory
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.widgets import SeekSlider, VideoSurface, format_time, glyph_icon

S = PlaybackState
SEEK_STEP_MS = 5_000
VOLUME_STEP = 5
POSITION_REFRESH_MS = 100
STATUS_REFRESH_TICKS = 10  # refresh engine diagnostics in the status bar about once a second
MEDIA_FILTER = (
    "Media files (*.mp4 *.m4v *.mkv *.mov *.avi *.wmv *.webm *.ts *.mts *.m2ts *.mpg *.mpeg *.vob "
    "*.ogv *.flv *.3gp *.mp3 *.m4a *.aac *.flac *.wav *.ogg *.opus *.wma *.ac3);;All files (*)"
)
_HAS_MEDIA = frozenset({S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED})
_SEEKABLE = frozenset({S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED})


def _named[W: QWidget](widget: W, name: str) -> W:
    """Set the Qt object name used by the stylesheet (PySide's stubs reject it as a constructor keyword)."""
    widget.setObjectName(name)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, factory: EngineFactory, icon: QIcon, engine_name: str = "libvlc") -> None:
        super().__init__()
        self._factory = factory
        self._engine_name = engine_name
        self._controller = PlaybackController(factory)
        self._events = UiBridge(self)
        self._events.delivered.connect(self._on_engine_event)
        self._controller.add_listener(self._events.post)
        self._engine_ready = UiBridge(self)
        self._engine_ready.delivered.connect(self._on_engine_created)
        self._engine_thread: threading.Thread | None = None
        self._engine_error: PlaybackError | None = None
        self._pending_open: str | None = None
        self._media_name = ""
        self._state = S.UNINITIALIZED
        self._duration_ms: int | None = None
        self._closing = False
        self._ticks = 0

        self.setWindowTitle(PRODUCT_NAME)
        self.setWindowIcon(icon)
        self.setMinimumSize(640, 400)
        self.resize(1100, 700)
        self.setAcceptDrops(True)

        root = _named(QWidget(), "root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._header = self._build_header(icon)
        layout.addWidget(self._header)
        layout.addWidget(self._build_stage(), stretch=1)
        self._controls = self._build_controls()
        layout.addWidget(self._controls)
        self.setCentralWidget(root)
        self._build_actions()
        self.statusBar().showMessage(f"Version {__version__} · Local-only · No telemetry")

        self._timer = QTimer(self)
        self._timer.setInterval(POSITION_REFRESH_MS)
        self._timer.timeout.connect(self._refresh_position)
        self._show_message("Starting playback engine…", "")
        self._apply_state(S.UNINITIALIZED)

    # ------------------------------------------------------------ layout
    def _build_header(self, icon: QIcon) -> QWidget:
        header = _named(QWidget(), "header")
        row = QHBoxLayout(header)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(icon.pixmap(36, 36))
        logo.setAccessibleName(f"{PRODUCT_NAME} logo")
        row.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(_named(QLabel(BRAND.upper()), "brand"))
        text.addWidget(_named(QLabel(PRODUCT_NAME), "productName"))
        row.addLayout(text)
        row.addStretch(1)
        row.addWidget(_named(QLabel(TAGLINE), "tagline"), alignment=Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_stage(self) -> QStackedWidget:
        self._stage = QStackedWidget()
        message_page = _named(QFrame(), "messagePage")
        box = QVBoxLayout(message_page)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_title = _named(QLabel(), "messageTitle")
        self._message_body = _named(QLabel(), "messageBody")
        for label in (self._message_title, self._message_body):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(label)
        self._video = VideoSurface()
        self._video.double_clicked.connect(self.toggle_fullscreen)
        self._stage.addWidget(message_page)
        self._stage.addWidget(self._video)
        return self._stage

    _FALLBACK_ICONS: ClassVar[dict[str, QStyle.StandardPixmap]] = {
        "open": QStyle.StandardPixmap.SP_DirOpenIcon,
        "play": QStyle.StandardPixmap.SP_MediaPlay,
        "pause": QStyle.StandardPixmap.SP_MediaPause,
        "stop": QStyle.StandardPixmap.SP_MediaStop,
        "volume": QStyle.StandardPixmap.SP_MediaVolume,
        "mute": QStyle.StandardPixmap.SP_MediaVolumeMuted,
        "fullscreen": QStyle.StandardPixmap.SP_TitleBarMaxButton,
        "exit_fullscreen": QStyle.StandardPixmap.SP_TitleBarNormalButton,
    }

    def _icon(self, name: str) -> QIcon:
        return glyph_icon(name, theme.TEXT, theme.BORDER) or self.style().standardIcon(
            self._FALLBACK_ICONS[name]
        )

    def _tool_button(self, icon: str, name: str, tip: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(self._icon(icon))
        button.setIconSize(QSize(20, 20))
        button.setAccessibleName(name)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keep Space/arrows for the window shortcuts
        return button

    def _build_controls(self) -> QWidget:
        bar = _named(QFrame(), "controlBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(8)
        self._open_button = self._tool_button("open", "Open file", "Open file (Ctrl+O)")
        self._open_button.clicked.connect(self.choose_file)
        self._play_button = self._tool_button("play", "Play", "Play/Pause (Space)")
        self._play_button.clicked.connect(self.toggle_play_pause)
        self._stop_button = self._tool_button("stop", "Stop", "Stop")
        self._stop_button.clicked.connect(self.stop)
        self._time_label = _named(QLabel(format_time(0)), "timeLabel")
        self._seek = SeekSlider()
        self._seek.seek_requested.connect(self.seek_to)
        self._duration_label = _named(QLabel(format_time(None)), "timeLabel")
        self._mute_button = self._tool_button("volume", "Mute", "Mute (M)")
        self._mute_button.clicked.connect(self.toggle_mute)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(100)
        self._volume.setFixedWidth(100)
        self._volume.setAccessibleName("Volume")
        self._volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._volume.valueChanged.connect(self.set_volume)
        self._fullscreen_button = self._tool_button("fullscreen", "Fullscreen", "Fullscreen (F)")
        self._fullscreen_button.clicked.connect(self.toggle_fullscreen)
        for widget in (self._open_button, self._play_button, self._stop_button, self._time_label):
            row.addWidget(widget)
        row.addWidget(self._seek, stretch=1)
        for trailing in (self._duration_label, self._mute_button, self._volume, self._fullscreen_button):
            row.addWidget(trailing)
        return bar

    def _action(self, text: str, keys: list[QKeySequence], slot: object) -> QAction:
        action = QAction(text, self)
        action.setShortcuts(keys)
        action.triggered.connect(slot)
        self.addAction(action)  # shortcuts keep working while the menu bar is hidden in fullscreen
        return action

    def _build_actions(self) -> None:
        K = QKeySequence
        self.open_action = self._action("&Open file…", [K(K.StandardKey.Open)], self.choose_file)
        quit_action = self._action("E&xit", [K("Ctrl+Q")], self.close)
        self.play_action = self._action(
            "&Play/Pause", [K(Qt.Key.Key_Space), K(Qt.Key.Key_MediaTogglePlayPause)], self.toggle_play_pause
        )
        self.stop_action = self._action("&Stop", [K(Qt.Key.Key_MediaStop)], self.stop)
        self.back_action = self._action(
            "Back 5 s", [K(Qt.Key.Key_Left)], lambda: self.seek_relative(-SEEK_STEP_MS)
        )
        self.forward_action = self._action(
            "Forward 5 s", [K(Qt.Key.Key_Right)], lambda: self.seek_relative(SEEK_STEP_MS)
        )
        vol_up = self._action("Volume up", [K(Qt.Key.Key_Up)], lambda: self.step_volume(VOLUME_STEP))
        vol_down = self._action("Volume down", [K(Qt.Key.Key_Down)], lambda: self.step_volume(-VOLUME_STEP))
        mute = self._action("&Mute", [K(Qt.Key.Key_M)], self.toggle_mute)
        self.fullscreen_action = self._action(
            "&Fullscreen", [K(Qt.Key.Key_F), K(Qt.Key.Key_F11)], self.toggle_fullscreen
        )
        self._action("Exit fullscreen", [K(Qt.Key.Key_Escape)], self.exit_fullscreen)
        about = QAction(f"&About {PRODUCT_NAME}", self)
        about.triggered.connect(self._show_about)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        play_menu = self.menuBar().addMenu("&Playback")
        for action in (self.play_action, self.stop_action, self.back_action, self.forward_action):
            play_menu.addAction(action)
        play_menu.addSeparator()
        for action in (vol_up, vol_down, mute):
            play_menu.addAction(action)
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.fullscreen_action)
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(about)

    # ----------------------------------------------------------- engine
    @property
    def controller(self) -> PlaybackController:
        return self._controller

    def start_engine(self) -> None:
        """Create the engine on a worker thread; the UI stays responsive while the DLL loads."""
        self._controller.set_video_output(int(self._video.winId()))

        def work() -> None:
            try:
                self._engine_ready.post(self._factory.create(self._engine_name))
            except PlaybackError as exc:
                self._engine_ready.post(exc)

        self._engine_thread = threading.Thread(target=work, name="engine-start", daemon=True)
        self._engine_thread.start()

    def _on_engine_created(self, result: object) -> None:
        if isinstance(result, PlaybackError):
            self._engine_error = result
            self._show_message("Playback engine unavailable", f"{result.user_message}\n{result.detail}")
            self._apply_state(S.UNINITIALIZED)
            return
        if not isinstance(result, PlaybackEngine):
            return
        if self._closing:
            result.close()  # the window closed while the engine was starting
            return
        self._controller.attach(result)
        caps = result.get_capabilities()
        self.statusBar().showMessage(f"{caps.engine_name} {caps.engine_version} · Local-only · No telemetry")
        self._show_message("Open a file to start", "Ctrl+O, or drag a file onto this window")
        self._apply_state(S.READY)
        self._timer.start()
        if self._pending_open:
            path, self._pending_open = self._pending_open, None
            self.open_path(path)

    # --------------------------------------------------------- commands
    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open media", "", MEDIA_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if self._controller.engine_name is None:
            self._pending_open = path  # opened once the engine is ready
            return
        self._media_name = Path(path).name if "://" not in path else path
        self._duration_ms = None
        # Update the window first: an engine may report failure while open() is still running,
        # and the (queued) error event must win over these defaults.
        self.setWindowTitle(f"{self._media_name} — {PRODUCT_NAME}")
        self._stage.setCurrentWidget(self._video)
        try:
            self._controller.open(path)
        except PlaybackError as exc:
            self._show_error(exc)

    def toggle_play_pause(self) -> None:
        if self._state in (S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED, S.LOADING) or (
            self._state is S.READY and self._media_name
        ):
            self._run(self._controller.toggle_play_pause)

    def stop(self) -> None:
        if self._state in _HAS_MEDIA or self._state is S.ERROR:
            self._run(self._controller.stop)

    def seek_to(self, position_ms: int) -> None:
        if self._state in _SEEKABLE:
            self._run(
                lambda: self._controller.seek(max(0, min(position_ms, self._duration_ms or position_ms)))
            )

    def seek_relative(self, delta_ms: int) -> None:
        if self._state in _SEEKABLE:
            self.seek_to(self._controller.status().position_ms + delta_ms)

    def set_volume(self, level: int) -> None:
        if self._controller.engine_name is not None:
            self._run(lambda: self._controller.set_volume(level))
            if level > 0 and self._controller.status().muted:
                self.toggle_mute()

    def step_volume(self, delta: int) -> None:
        self._volume.setValue(max(0, min(100, self._volume.value() + delta)))

    def toggle_mute(self) -> None:
        if self._controller.engine_name is None:
            return
        muted = not self._controller.status().muted
        self._run(lambda: self._controller.set_muted(muted))
        self._mute_button.setIcon(self._icon("mute" if muted else "volume"))
        self._mute_button.setAccessibleName("Unmute" if muted else "Mute")

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            for widget in (self._header, self.menuBar(), self.statusBar()):
                widget.hide()
            self._fullscreen_button.setIcon(self._icon("exit_fullscreen"))
            self.showFullScreen()

    def exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            for widget in (self._header, self.menuBar(), self.statusBar()):
                widget.show()
            self._fullscreen_button.setIcon(self._icon("fullscreen"))

    def _run(self, command: object) -> None:
        """Run a controller command; report refused commands instead of raising into Qt."""
        try:
            command()  # type: ignore[operator]
        except PlaybackError as exc:
            self.statusBar().showMessage(exc.user_message, 4000)

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
        ready = self._controller.engine_name is not None
        has_media = state in _HAS_MEDIA or (state is S.READY and bool(self._media_name))
        self.open_action.setEnabled(ready)
        self._open_button.setEnabled(ready)
        self._play_button.setEnabled(ready and has_media)
        self.play_action.setEnabled(ready and has_media)
        can_stop = ready and (state in _HAS_MEDIA or state is S.ERROR)
        self._stop_button.setEnabled(can_stop)
        self.stop_action.setEnabled(can_stop)
        seekable = ready and state in _SEEKABLE and bool(self._duration_ms)
        self._seek.setEnabled(seekable)
        self.back_action.setEnabled(seekable)
        self.forward_action.setEnabled(seekable)
        playing = state in (S.PLAYING, S.BUFFERING)
        self._play_button.setIcon(self._icon("pause" if playing else "play"))
        self._play_button.setAccessibleName("Pause" if playing else "Play")
        status = {
            S.LOADING: f"Opening {self._media_name}…",
            S.BUFFERING: "Buffering…",
            S.PAUSED: "Paused",
            S.ENDED: "Ended",
        }.get(state)
        if status:
            self.statusBar().showMessage(status)
        elif state is S.PLAYING:
            self._show_engine_status()
        if state is S.READY and self._media_name:
            self._show_message(self._media_name, "Stopped")
            self._seek.setValue(0)
            self._time_label.setText(format_time(0))

    def _apply_media_info(self, info: MediaInfo) -> None:
        self._duration_ms = info.duration_ms
        self._seek.setRange(0, info.duration_ms or 0)
        self._duration_label.setText(format_time(info.duration_ms))
        if info.video_codec is None and info.audio_codec is not None:
            self._show_message(f"♪  {self._media_name}", f"Audio · {info.audio_codec}")
        elif self._state in (S.PLAYING, S.PAUSED, S.BUFFERING, S.LOADING):
            self._stage.setCurrentWidget(self._video)
        self._apply_state(self._state)
        self._show_engine_status()

    def _show_engine_status(self) -> None:
        if self._controller.engine_name is None:
            return
        info = self._controller.media_info()
        diag = self._controller.engine.diagnostics()
        parts = [diag.get("engine", "")]
        if info and info.video_codec:
            parts.append(f"{info.video_codec} {info.width}x{info.height}")
            parts.append(f"decoder: {diag.get('hwdec', 'unknown').split(' (')[0]}")
        if info and info.audio_codec:
            parts.append(info.audio_codec)
        self.statusBar().showMessage(" · ".join(p for p in parts if p))

    def _show_error(self, error: PlaybackError) -> None:
        self._show_message(
            error.user_message, f"{self._media_name}\n{error.detail}" if self._media_name else ""
        )
        self.statusBar().showMessage(error.user_message)
        self.setWindowTitle(PRODUCT_NAME)

    def _show_message(self, title: str, body: str) -> None:
        self._message_title.setText(title)
        self._message_body.setText(body)
        self._stage.setCurrentIndex(0)

    def _refresh_position(self) -> None:
        if self._controller.engine_name is None or self._state not in _HAS_MEDIA:
            return
        status = self._controller.status()
        if status.duration_ms and status.duration_ms != self._duration_ms:
            self._duration_ms = status.duration_ms
            self._seek.setRange(0, status.duration_ms)
            self._duration_label.setText(format_time(status.duration_ms))
            self._apply_state(self._state)
        if not self._seek.user_dragging:
            self._seek.setValue(status.position_ms)
        self._time_label.setText(
            format_time(self._seek.value() if self._seek.user_dragging else status.position_ms)
        )
        # Engines report some diagnostics (e.g. the hardware decoder) after playback starts.
        self._ticks += 1
        if status.state is S.PLAYING and self._ticks % STATUS_REFRESH_TICKS == 0:
            self._show_engine_status()

    # ------------------------------------------------------------ window
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if self._controller.engine_name is not None and urls and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.open_path(urls[0].toLocalFile())
            event.acceptProposedAction()

    def _show_about(self) -> None:
        engine = ""
        if self._controller.engine_name is not None:
            caps = self._controller.capabilities()
            engine = f"<br>Playback engine: {caps.engine_name} {caps.engine_version}"
        QMessageBox.about(
            self,
            f"About {PRODUCT_NAME}",
            f"<b>{PRODUCT_NAME}</b> {__version__}<br>{TAGLINE}<br><br>"
            f"Free, no ads, no account, no telemetry.{engine}",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        # Rule: the engine must be closed while its host window still exists.
        self._closing = True
        self._timer.stop()
        self._controller.shutdown()
        if self._engine_thread is not None:
            self._engine_thread.join(timeout=10)
        super().closeEvent(event)
