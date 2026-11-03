"""Now Playing page: video surface, state messages and the control bar, wired to the controller.

Engine events arrive on engine threads and are marshalled through ``UiBridge``. Position is
polled (``POSITION_REFRESH_MS``) rather than pushed. The engine is created on a worker
thread and must be shut down (``shutdown()``) while the window still exists.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.configuration.preferences import Preferences, language_matches
from babarify_frame.core.enhancements import (
    PICTURE_RANGES,
    EqualizerSettings,
    PictureSettings,
    VideoTransform,
)
from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.events import ErrorOccurred, MediaInfoChanged, Notice, StateChanged
from babarify_frame.core.models import (
    Chapter,
    EngineCapabilities,
    EngineOptions,
    MediaInfo,
    PlaybackState,
    TrackInfo,
    TrackKind,
)
from babarify_frame.core.network import is_network_uri, stream_display_name
from babarify_frame.library.database import LibraryDatabase, LibraryError
from babarify_frame.library.history import SAVE_INTERVAL_MS, resume_position
from babarify_frame.library.models import Bookmark
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.controller import PlaybackController
from babarify_frame.playback.factory import EngineFactory
from babarify_frame.playback.preview import FramePreview
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.controls import VOLUME_MIN, ControlBar
from babarify_frame.ui.seek_preview import PreviewPopup, SeekPreview
from babarify_frame.ui.subtitles import (
    DELAY_STEP_MS,
    SyncDialog,
    build_tracks_menu,
    format_delay,
    track_label,
)
from babarify_frame.ui.widgets import VideoSurface, format_time, glyph_icon, plain_text

log = logging.getLogger(__name__)


def snapshot_folder() -> Path:
    """Pictures\\Babarify Frame (BABARIFY_SNAPSHOT_DIR overrides it, e.g. for tests)."""
    override = os.environ.get("BABARIFY_SNAPSHOT_DIR")
    if override:
        return Path(override)
    return Path.home() / "Pictures" / "Babarify Frame"


S = PlaybackState
POSITION_REFRESH_MS = 100
STATUS_REFRESH_TICKS = 10  # refresh engine diagnostics about once a second
CURSOR_POLL_MS = 200
VOLUME_STEP = 5
HAS_MEDIA = frozenset({S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED})
SEEKABLE = frozenset({S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED})
TRACK_STATES = frozenset({S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED})  # engines accept track changes
CHAPTER_RESTART_MS = 3000  # "previous chapter" within this of a chapter start goes one further back


@dataclass(frozen=True)
class _TrackResume:
    """Audio/subtitle choices carried across an engine restart (e.g. a subtitle style change)."""

    audio_id: int | None
    subtitle_id: int | None
    external_subtitle: str | None  # re-loaded when the selected subtitle came from a file
    subtitle_delay_ms: int
    audio_delay_ms: int


class PlayerPage(QWidget):
    status_changed = Signal(str)
    title_changed = Signal(str)  # media name, "" when nothing is open
    state_changed = Signal(object)  # PlaybackState
    engine_ready = Signal(bool)
    video_started = Signal()  # first frame of a video (not audio-only) after open
    open_requested = Signal()
    subtitle_file_requested = Signal()  # the window shows the file dialog
    fullscreen_requested = Signal()
    history_changed = Signal()  # a play was recorded or a position saved (M6)
    picture_changed = Signal(object)  # PictureSettings (M7), for the window to persist
    equalizer_changed = Signal(object)  # EqualizerSettings
    enhancements_reset = Signal()  # the engine was (re)created: refresh controls from capabilities
    bookmarks_changed = Signal()  # M8: the current file's bookmarks changed (or another file opened)
    media_info_changed = Signal()  # M8: tracks, tags or chapters of the current file changed

    def __init__(
        self,
        factory: EngineFactory,
        engine_name: str,
        prefs: Preferences,
        parent: QWidget | None = None,
        history: LibraryDatabase | None = None,
        preview_factory: Callable[[], FramePreview] | None = None,
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
        self._resume_tracks: _TrackResume | None = None
        self._tracks_applied = False  # preferences/resume applied to this file's tracks
        self._embedded_subtitle_ids: set[int] = set()
        self._external_subtitles: list[str] = []
        self._sync_dialog: SyncDialog | None = None
        # History and queue (M6)
        self._history = history
        self._current_uri: str | None = None
        self._play_recorded = False
        self._resumed_from_history = False
        self._queue: list[str] = []
        self._queue_index = -1
        # Picture and sound (M7)
        self._transform = VideoTransform.NONE  # this session only; applied when the engine is created
        self._geometry: tuple[str, str, float] = ("", "", 0.0)  # per file
        self._ab: tuple[int | None, int | None] = (None, None)  # A-B repeat points, per file
        # Advanced media (M8)
        self._bookmarks: list[Bookmark] = []
        self._preview = SeekPreview(preview_factory, self) if preview_factory is not None else None
        self._preview_path: str | None = None
        self._popup = PreviewPopup(self)
        self._hover: tuple[int, QPoint] | None = None
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
        plain_text(self._message_title, self._message_body)  # names and error details are untrusted
        for label in (self._message_icon, self._message_title, self._message_body):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            box.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._message_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._message_body.setMaximumWidth(640)
        # A word-wrapped label centred in a box is otherwise laid out too narrow and too short,
        # cutting off long reasons (M8 evidence: a network refusal lost its last line).
        self._message_body.setMinimumWidth(480)
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
        c.tracks_menu_opening.connect(self._fill_tracks_menu)
        c.seek.hovered.connect(self._on_seek_hover)
        c.seek.hover_left.connect(self._on_seek_left)
        if self._preview is not None:
            self._preview.frame_ready.connect(self._on_preview_frame)

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

        options = EngineOptions(
            hardware_decoding=self._prefs.hardware_decoding,
            subtitle_style=self._prefs.subtitle_style,
            video_transform=self._transform,
        )

        started = time.monotonic()

        def work() -> None:
            try:
                engine = self._factory.create(self._engine_name, options)
                log.info("%s engine ready in %.1f s", self._engine_name, time.monotonic() - started)
                self._engine_bridge.post(engine)
            except PlaybackError as exc:
                log.error("%s engine unavailable: %s", self._engine_name, exc)
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
        self._apply_enhancements()
        self.enhancements_reset.emit()
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
        self._save_history()
        status = self._controller.status() if self.engine_is_ready else None
        if status is not None and status.uri and self.has_media and self._state is not S.ERROR:
            self._resume = (status.uri, status.position_ms, status.state in (S.PLAYING, S.BUFFERING))
            self._resume_tracks = self._current_tracks(status.subtitle_delay_ms, status.audio_delay_ms)
        self._position_timer.stop()
        self._controller.shutdown()  # the video surface stays alive: close-before-window holds
        if self._engine_thread is not None:
            self._engine_thread.join(timeout=10)
        self._apply_state(S.UNINITIALIZED)
        self._show_message("info", "Restarting playback engine…", "")
        self.start_engine()  # actions update through state_changed; engine_ready(False) means failure

    def open_path(self, path: str, *, autoplay: bool = True, keep_queue: bool = False) -> None:
        if not keep_queue:
            self._queue, self._queue_index = [], -1
        if not self.engine_is_ready:
            self._pending_open = path  # opened once the engine is ready
            return
        if self._current_uri is not None and self._current_uri != path:
            self._save_history()  # the file being replaced keeps its place
        self._current_uri = path
        self._play_recorded = False
        self._resumed_from_history = False
        if self._resume_position is None and self._prefs.resume_playback:
            start = self._history_resume_point(path)
            if start:
                self._resume_position = start
                self._resumed_from_history = True
        if is_network_uri(path):
            self._media_name = stream_display_name(path)  # never the query: it can hold tokens
        else:
            self._media_name = Path(path).name if "://" not in path else path
        self._set_preview(None)
        self._load_bookmarks()
        self._geometry = ("", "", 0.0)  # aspect, crop and zoom belong to a file
        self._ab = (None, None)
        self._tracks_applied = False
        self._embedded_subtitle_ids = set()
        self._external_subtitles = []
        if self._sync_dialog is not None:
            self._sync_dialog.set_delays(0, 0)  # delays belong to a file
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
            return
        caps = self.capabilities_or_none()
        if caps is not None and caps.supports_aspect_ratio:
            self._run(lambda: self._controller.engine.set_video_geometry("", "", 0.0))

    def open_at(self, path: str, position_ms: int) -> None:
        """Open a file and start at a given time (e.g. a spoken-word search result, M9)."""
        self._resume_position = max(0, position_ms)
        self.open_path(path)

    @property
    def current_uri(self) -> str | None:
        return self._current_uri if self.has_media else None

    @property
    def media_name(self) -> str:
        return self._media_name

    def toggle_play_pause(self) -> None:
        if self.has_media and self._state is not S.ERROR:
            self._run(self._controller.toggle_play_pause)

    def stop(self) -> None:
        if self._state in HAS_MEDIA or self._state is S.ERROR:
            self._save_history()  # stopping resets the position to 0
            self._run(self._controller.stop)

    def start_over(self) -> None:
        """Back to the beginning (e.g. after an automatic resume)."""
        if self._state in SEEKABLE:
            self.seek_to(0)
            self.status_changed.emit("From the beginning")

    # --------------------------------------------- chapters and bookmarks (M8)
    @property
    def chapters(self) -> tuple[Chapter, ...]:
        info = self._controller.media_info() if self.engine_is_ready else None
        return info.chapters if info is not None and self.has_media else ()

    def current_chapter(self) -> Chapter | None:
        info = self._controller.media_info() if self.engine_is_ready else None
        if info is None or not info.chapters:
            return None
        return info.chapter_at(self._controller.status().position_ms)

    def jump_to_chapter(self, index: int) -> None:
        chapters = self.chapters
        if 0 <= index < len(chapters) and self.is_seekable:
            chapter = chapters[index]
            self.seek_to(chapter.start_ms)
            self.status_changed.emit(f"Chapter {index + 1} of {len(chapters)}: {chapter.label}")

    def next_chapter(self) -> None:
        position = self._controller.status().position_ms if self.engine_is_ready else 0
        later = [c for c in self.chapters if c.start_ms > position + 500]
        if later:
            self.jump_to_chapter(later[0].index)
        elif self.chapters:
            self.status_changed.emit("Last chapter")

    def previous_chapter(self) -> None:
        current = self.current_chapter()
        if current is None:
            return
        position = self._controller.status().position_ms
        if position - current.start_ms > CHAPTER_RESTART_MS or current.index == 0:
            self.jump_to_chapter(current.index)
        else:
            self.jump_to_chapter(current.index - 1)

    @property
    def bookmarks(self) -> list[Bookmark]:
        return list(self._bookmarks)

    @property
    def can_bookmark(self) -> bool:
        return self._history is not None and self._current_uri is not None and self.is_seekable

    def _load_bookmarks(self) -> None:
        self._bookmarks = []
        if self._history is not None and self._current_uri is not None:
            try:
                self._bookmarks = self._history.bookmarks_for(self._current_uri)
            except sqlite3.Error:
                log.exception("could not read bookmarks")
        self._update_marks()
        self.bookmarks_changed.emit()

    def add_bookmark(self, label: str = "") -> Bookmark | None:
        if not self.can_bookmark or self._history is None or self._current_uri is None:
            return None
        position = self._controller.status().position_ms
        try:
            bookmark = self._history.add_bookmark(self._current_uri, position, label)
        except LibraryError as exc:
            self.status_changed.emit(str(exc))
            return None
        except sqlite3.Error:
            log.exception("could not add bookmark")
            self.status_changed.emit("The bookmark could not be saved")
            return None
        self._load_bookmarks()
        self.status_changed.emit(f"Bookmark added at {format_time(position)}")
        return bookmark

    def rename_bookmark(self, bookmark_id: int, label: str) -> None:
        if self._history is not None:
            self._history.rename_bookmark(bookmark_id, label)
            self._load_bookmarks()

    def delete_bookmark(self, bookmark_id: int) -> None:
        if self._history is not None:
            self._history.delete_bookmark(bookmark_id)
            self._load_bookmarks()

    def _update_marks(self) -> None:
        chapters = tuple(c.start_ms for c in self.chapters)
        self.controls.seek.set_marks(chapters, tuple(b.position_ms for b in self._bookmarks))

    # ------------------------------------------------- seek previews (M8)
    @property
    def preview(self) -> SeekPreview | None:
        return self._preview

    def _set_preview(self, path: str | None) -> None:
        if self._preview is None:
            return
        if path is not None and not self._prefs.seek_previews:
            path = None
        if path == self._preview_path:
            return
        self._preview_path = path
        self._preview.set_media(path, self._duration_ms if path else None)

    def _hover_text(self, position_ms: int) -> str:
        info = self._controller.media_info() if self.engine_is_ready else None
        chapter = info.chapter_at(position_ms) if info is not None else None
        text = format_time(position_ms)
        return f"{text} · {chapter.label}" if chapter is not None else text

    def _on_seek_hover(self, position_ms: int, anchor: QPoint) -> None:
        if not self.is_seekable:
            return
        self._hover = (position_ms, anchor)
        pixmap = (
            self._preview.request(position_ms) if self._preview is not None and self._preview_path else None
        )
        self._popup.show_at(anchor, self._hover_text(position_ms), pixmap)

    def _on_seek_left(self) -> None:
        self._hover = None
        self._popup.hide()

    def _on_preview_frame(self, bucket: int) -> None:
        if self._hover is None or self._preview is None:
            return
        position, anchor = self._hover
        if self._preview.bucket_of(position) == bucket:
            self._popup.show_at(anchor, self._hover_text(position), self._preview.pixmap(bucket))

    # ---------------------------------------------------- history (M6)
    @property
    def history_enabled(self) -> bool:
        return self._history is not None and self._prefs.remember_history

    def _history_resume_point(self, path: str) -> int:
        if not self.history_enabled or self._history is None:
            return 0
        try:
            entry = self._history.history_for(path)
        except sqlite3.Error:
            log.exception("history lookup failed")
            return 0
        if entry is None:
            return 0
        return resume_position(entry.position_ms, entry.duration_ms, entry.finished)

    def _save_history(self) -> None:
        """Save the current file's position. Never raises: history must not break playback."""
        uri = self._current_uri
        if not self.history_enabled or self._history is None or uri is None or not self.engine_is_ready:
            return
        if not self._play_recorded or self._state not in (S.PLAYING, S.PAUSED, S.BUFFERING):
            return
        status = self._controller.status()
        try:
            self._history.save_position(uri, self._media_name, status.position_ms, status.duration_ms)
        except sqlite3.Error:
            log.exception("could not save playback position")
            return
        self.history_changed.emit()

    def _record_play(self) -> None:
        uri = self._current_uri
        if self._play_recorded or uri is None:
            return
        self._play_recorded = True
        if not self.history_enabled or self._history is None:
            return
        try:
            self._history.record_play(uri, self._media_name, self._duration_ms)
        except sqlite3.Error:
            log.exception("could not record play")
            return
        self.history_changed.emit()

    def _record_finished(self) -> None:
        if self.history_enabled and self._history is not None and self._current_uri and self._play_recorded:
            try:
                self._history.mark_finished(self._current_uri)
            except sqlite3.Error:
                log.exception("could not mark finished")
                return
            self.history_changed.emit()

    # ------------------------------------------------------ queue (M6)
    @property
    def queue(self) -> tuple[list[str], int]:
        return list(self._queue), self._queue_index

    def play_queue(self, paths: list[str], start: int = 0) -> None:
        """Play a list of files in order (a playlist). Unavailable files are skipped."""
        if not paths:
            return
        self._queue = list(paths)
        self._queue_index = max(0, min(start, len(paths) - 1)) - 1
        self.next_in_queue()

    def next_in_queue(self) -> None:
        self._step_queue(1)

    def previous_in_queue(self) -> None:
        self._step_queue(-1)

    def _step_queue(self, direction: int) -> None:
        if not self._queue:
            self.status_changed.emit("No playlist is playing")
            return
        index = self._queue_index + direction
        skipped = 0
        while 0 <= index < len(self._queue):
            path = self._queue[index]
            if "://" in path or os.path.exists(path):
                self._queue_index = index
                self.open_path(path, keep_queue=True)
                note = f" (skipped {skipped} missing)" if skipped else ""
                self.status_changed.emit(
                    f"Playlist {index + 1} of {len(self._queue)}: {self._media_name}{note}"
                )
                return
            skipped += 1
            index += direction
        self.status_changed.emit("End of playlist" if direction > 0 else "Start of playlist")

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
        level = max(VOLUME_MIN, level)
        self.controls.set_volume(level)
        if self.engine_is_ready:
            self._run(lambda: self._controller.set_volume(level))
            if level > 0 and self._controller.status().muted:
                self.toggle_mute()

    def step_volume(self, delta: int) -> None:
        self._show_controls()  # the number must be visible while the keys change it in fullscreen
        value = self.controls.volume.value()
        base = 0 if value == VOLUME_MIN else value  # so steps from the bottom go 1, 5, 10
        self.set_volume(min(self.volume_maximum, base + delta))

    @property
    def volume_maximum(self) -> int:
        """100, or 200 with volume boost allowed (and supported by the engine)."""
        if not self._prefs.allow_volume_boost:
            return 100
        caps = self.capabilities_or_none()
        return min(200, caps.max_volume) if caps is not None else 100

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
            return min(100, status.volume), status.muted  # a boost is never remembered
        return self.controls.volume.value(), self._prefs.muted

    def set_preferences(self, prefs: Preferences) -> None:
        boost_changed = prefs.allow_volume_boost != self._prefs.allow_volume_boost
        style_changed = prefs.subtitle_style != self._prefs.subtitle_style
        restart = self.engine_is_ready and (
            prefs.hardware_decoding != self._prefs.hardware_decoding
            or (style_changed and self._controller.capabilities().subtitle_style == "restart")
        )
        previews_changed = prefs.seek_previews != self._prefs.seek_previews
        self._prefs = prefs
        if previews_changed:
            info = self._controller.media_info() if self.engine_is_ready else None
            if prefs.seek_previews and info is not None:
                self._apply_media_info(info)  # starts previews for a local video
            else:
                self._set_preview(None)
        if boost_changed:
            self.controls.set_volume_maximum(self.volume_maximum)
            if self.controls.volume.value() > self.volume_maximum:
                self.set_volume(self.volume_maximum)
        if restart:
            self.restart_engine()
        elif (
            style_changed
            and self.engine_is_ready
            and self._state in HAS_MEDIA
            and self._controller.capabilities().subtitle_style == "live"
        ):
            self._run(lambda: self._controller.set_subtitle_style(prefs.subtitle_style))

    # ---------------------------------------------- picture and sound (M7)
    def capabilities_or_none(self) -> EngineCapabilities | None:
        return self._controller.capabilities() if self.engine_is_ready else None

    @property
    def transform(self) -> VideoTransform:
        return self._transform

    @property
    def video_geometry(self) -> tuple[str, str, float]:
        return self._geometry

    def _supported_picture(self, picture: PictureSettings) -> PictureSettings:
        """Unsupported adjustments fall back to their defaults instead of failing."""
        caps = self.capabilities_or_none()
        if caps is None:
            return picture
        values = {
            name: getattr(picture, name) if name in caps.picture_adjustments else default
            for name, (default, _low, _high) in PICTURE_RANGES.items()
        }
        return PictureSettings(**values)

    def _apply_enhancements(self) -> None:
        caps = self.capabilities_or_none()
        if caps is None:
            return
        self.controls.set_volume_maximum(self.volume_maximum)
        if caps.picture_adjustments:
            self._run(
                lambda: self._controller.engine.set_picture(self._supported_picture(self._prefs.picture))
            )
        if caps.supports_equalizer:
            self._run(lambda: self._controller.engine.set_equalizer(self._prefs.equalizer))

    def set_picture(self, picture: PictureSettings) -> None:
        picture = self._supported_picture(picture.normalized())
        self._prefs = replace(self._prefs, picture=picture)
        if self.engine_is_ready:
            self._run(lambda: self._controller.engine.set_picture(picture))
        self.picture_changed.emit(picture)

    def set_equalizer(self, equalizer: EqualizerSettings) -> None:
        equalizer = equalizer.normalized()
        self._prefs = replace(self._prefs, equalizer=equalizer)
        caps = self.capabilities_or_none()
        if caps is not None and caps.supports_equalizer:
            self._run(lambda: self._controller.engine.set_equalizer(equalizer))
        self.equalizer_changed.emit(equalizer)

    def set_geometry(self, aspect: str, crop: str, zoom: float) -> None:
        if not self.engine_is_ready:
            return
        try:
            self._controller.engine.set_video_geometry(aspect, crop, zoom)
        except PlaybackError as exc:
            self.status_changed.emit(f"{exc.user_message.rstrip('.')}: {exc.detail}")
            return
        self._geometry = (aspect, crop, zoom)

    def set_transform(self, transform: VideoTransform) -> None:
        """Rotation/flip. Engines that apply it only when created are restarted at the same place."""
        if transform is self._transform:
            return
        caps = self.capabilities_or_none()
        self._transform = transform
        if caps is None:
            return
        if caps.rotation == "live":
            self._run(lambda: self._controller.engine.set_rotation(transform))
        elif caps.rotation == "restart":
            self.restart_engine()
        else:
            self._transform = VideoTransform.NONE
            self.status_changed.emit("Rotation is not supported by this playback engine")

    def frame_step(self, backward: bool = False) -> None:
        if self._state not in (S.PLAYING, S.PAUSED):
            return
        try:
            self._controller.engine.frame_step(backward)
        except PlaybackError as exc:
            self.status_changed.emit(f"{exc.user_message.rstrip('.')}: {exc.detail}")
            return
        self.status_changed.emit("Previous frame" if backward else "Next frame")

    def take_snapshot(self, folder: Path | None = None) -> Path | None:
        """Save the current frame as PNG in Pictures\\Babarify Frame (local, user-initiated)."""
        if self._state not in (S.PLAYING, S.PAUSED, S.BUFFERING):
            return None
        target_dir = folder or snapshot_folder()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.status_changed.emit(f"Could not create {target_dir}: {exc.strerror}")
            return None
        status = self._controller.status()
        stem = Path(self._media_name).stem if "://" not in self._media_name else "snapshot"
        safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in stem)[:80] or "snapshot"
        stamp = format_time(status.position_ms).replace(":", "-")
        path = target_dir / f"{safe} {stamp}.png"
        index = 2
        while path.exists():
            path = target_dir / f"{safe} {stamp} ({index}).png"
            index += 1
        try:
            self._controller.engine.take_snapshot(str(path))
        except PlaybackError as exc:
            self.status_changed.emit(f"{exc.user_message.rstrip('.')}: {exc.detail}")
            return None
        self.status_changed.emit(f"Snapshot saved: {path}")
        return path

    @property
    def ab_loop(self) -> tuple[int | None, int | None]:
        return self._ab

    def ab_loop_step(self) -> None:
        """First press sets A, second sets B (repeat starts), third clears."""
        if self._state not in SEEKABLE:
            return
        position = self._controller.status().position_ms
        a, b = self._ab
        if a is None:
            self._ab = (position, None)
            self.status_changed.emit(f"Repeat: A at {format_time(position)} · press again to set B")
        elif b is None:
            if position <= a + 500:
                self.status_changed.emit("B must be later than A")
                return
            self._ab = (a, position)
            self.status_changed.emit(
                f"Repeating {format_time(a)} to {format_time(position)} · press again to stop"
            )
            self.seek_to(a)
        else:
            self._ab = (None, None)
            self.status_changed.emit("Repeat off")

    def _check_ab_loop(self, position_ms: int) -> None:
        a, b = self._ab
        if a is not None and b is not None and position_ms >= b:
            self.seek_to(a)

    # -------------------------------------------------- audio and subtitles
    @property
    def can_change_tracks(self) -> bool:
        return self.engine_is_ready and self._state in TRACK_STATES

    @property
    def can_load_subtitles(self) -> bool:
        return self.can_change_tracks and self._controller.capabilities().supports_external_subtitles

    def _tracks(self, kind: TrackKind) -> list[TrackInfo]:
        info = self._controller.media_info() if self.engine_is_ready else None
        return list(info.tracks_of(kind)) if info else []

    def select_audio(self, track_id: int) -> None:
        if self.can_change_tracks:
            self._run(lambda: self._controller.select_audio_track(track_id))

    def select_subtitle(self, track_id: int | None) -> None:
        if self.can_change_tracks:
            self._run(lambda: self._controller.select_subtitle_track(track_id))

    def load_subtitle_file(self, path: str) -> None:
        """Add a local subtitle file to the playing media. Failures are reported, never raised."""
        if not self.can_load_subtitles:
            self.status_changed.emit("Open a video before loading subtitles")
            return
        name = Path(path).name
        # Before the call: an engine may report an unreadable file (Notice) before it returns.
        self.status_changed.emit(f"Loading subtitles from {name}…")
        try:
            self._controller.add_subtitle_file(path)
        except PlaybackError as exc:
            reason = name if exc.code is ErrorCode.MEDIA_NOT_FOUND or not exc.detail else exc.detail
            self.status_changed.emit(f"{exc.user_message.rstrip('.')}: {reason}")
            return
        self._external_subtitles.append(path)

    def cycle_subtitles(self) -> None:
        """Off → each track in order → Off."""
        tracks = self._tracks(TrackKind.SUBTITLE)
        if not self.can_change_tracks or not tracks:
            self.status_changed.emit("No subtitle tracks")
            return
        ids: list[int | None] = [None, *(t.id for t in tracks)]
        current = next((t.id for t in tracks if t.selected), None)
        target = ids[(ids.index(current) + 1) % len(ids)]
        self.select_subtitle(target)
        label = next((track_label(t, i) for i, t in enumerate(tracks, 1) if t.id == target), "Off")
        self.status_changed.emit(f"Subtitles: {label}")

    def cycle_audio(self) -> None:
        tracks = self._tracks(TrackKind.AUDIO)
        if not self.can_change_tracks or len(tracks) < 2:
            self.status_changed.emit("Only one audio track" if tracks else "No audio tracks")
            return
        current = next((i for i, t in enumerate(tracks) if t.selected), -1)
        index = (current + 1) % len(tracks)
        self.select_audio(tracks[index].id)
        self.status_changed.emit(f"Audio: {track_label(tracks[index], index + 1)}")

    def set_subtitle_delay(self, delay_ms: int) -> None:
        self._set_delay(delay_ms, subtitle=True)

    def set_audio_delay(self, delay_ms: int) -> None:
        self._set_delay(delay_ms, subtitle=False)

    def step_subtitle_delay(self, steps: int) -> None:
        if self.engine_is_ready:
            self.set_subtitle_delay(self._controller.status().subtitle_delay_ms + steps * DELAY_STEP_MS)

    def step_audio_delay(self, steps: int) -> None:
        if self.engine_is_ready:
            self.set_audio_delay(self._controller.status().audio_delay_ms + steps * DELAY_STEP_MS)

    def _set_delay(self, delay_ms: int, *, subtitle: bool) -> None:
        if not self.engine_is_ready or self._state not in HAS_MEDIA:
            return
        limit = self._controller.capabilities().max_delay_ms
        value = max(-limit, min(limit, int(delay_ms)))
        if subtitle:
            self._run(lambda: self._controller.set_subtitle_delay(value))
        else:
            self._run(lambda: self._controller.set_audio_delay(value))
        status = self._controller.status()
        if self._sync_dialog is not None:
            self._sync_dialog.set_delays(status.subtitle_delay_ms, status.audio_delay_ms)
        current = status.subtitle_delay_ms if subtitle else status.audio_delay_ms
        what = "Subtitle delay" if subtitle else "Audio delay"
        self.status_changed.emit(f"{what}: {format_delay(current)}")

    def show_sync_dialog(self) -> SyncDialog:
        if self._sync_dialog is None:
            limit = self._controller.capabilities().max_delay_ms if self.engine_is_ready else 60_000
            self._sync_dialog = SyncDialog(self, limit)
            self._sync_dialog.subtitle_delay_changed.connect(self.set_subtitle_delay)
            self._sync_dialog.audio_delay_changed.connect(self.set_audio_delay)
        if self.engine_is_ready:
            status = self._controller.status()
            self._sync_dialog.set_delays(status.subtitle_delay_ms, status.audio_delay_ms)
        self._sync_dialog.set_enabled_rows(self.engine_is_ready and self._state in HAS_MEDIA)
        self._sync_dialog.show()
        self._sync_dialog.raise_()
        return self._sync_dialog

    def _fill_tracks_menu(self, menu: QMenu) -> None:
        build_tracks_menu(
            menu,
            self._controller.media_info() if self.can_change_tracks else None,
            can_load_file=self.can_load_subtitles,
            on_audio=self.select_audio,
            on_subtitle=self.select_subtitle,
            on_load_file=self.subtitle_file_requested.emit,
            on_sync=self.show_sync_dialog,
        )

    def _current_tracks(self, subtitle_delay_ms: int, audio_delay_ms: int) -> _TrackResume:
        audio = next((t.id for t in self._tracks(TrackKind.AUDIO) if t.selected), None)
        sub = next((t.id for t in self._tracks(TrackKind.SUBTITLE) if t.selected), None)
        external = None
        if sub is not None and sub not in self._embedded_subtitle_ids and self._external_subtitles:
            external, sub = self._external_subtitles[-1], None
        return _TrackResume(audio, sub, external, subtitle_delay_ms, audio_delay_ms)

    def _maybe_apply_tracks(self) -> None:
        """Once per file, when tracks are known and the engine accepts changes: restore the
        choices from before a restart, or apply the language preferences."""
        if self._tracks_applied or not self.can_change_tracks:
            return
        info = self._controller.media_info()
        if info is None or not info.tracks:
            return
        self._tracks_applied = True
        audio = list(info.tracks_of(TrackKind.AUDIO))
        subs = list(info.tracks_of(TrackKind.SUBTITLE))
        self._embedded_subtitle_ids = {t.id for t in subs}
        resume, self._resume_tracks = self._resume_tracks, None
        if resume is not None:
            if resume.audio_id is not None and any(t.id == resume.audio_id for t in audio):
                self.select_audio(resume.audio_id)
            if resume.external_subtitle:
                self.load_subtitle_file(resume.external_subtitle)
            elif resume.subtitle_id is None or any(t.id == resume.subtitle_id for t in subs):
                self.select_subtitle(resume.subtitle_id)
            if resume.subtitle_delay_ms:
                self._run(lambda: self._controller.set_subtitle_delay(resume.subtitle_delay_ms))
            if resume.audio_delay_ms:
                self._run(lambda: self._controller.set_audio_delay(resume.audio_delay_ms))
            return
        prefs = self._prefs
        wanted_audio = next(
            (t for t in audio if language_matches(prefs.preferred_audio_language, t.language)), None
        )
        if wanted_audio is not None and not wanted_audio.selected:
            self.select_audio(wanted_audio.id)
        if prefs.subtitles_auto and subs and not any(t.selected for t in subs):
            preferred = next(
                (t for t in subs if language_matches(prefs.preferred_subtitle_language, t.language)), None
            )
            self.select_subtitle((preferred or subs[0]).id)

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
        elif isinstance(event, Notice):
            # Non-fatal (e.g. an unreadable subtitle file): playback continues.
            self.status_changed.emit(event.message[:1].upper() + event.message[1:])

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
                if self._resumed_from_history:
                    self.status_changed.emit(f"Resumed at {format_time(position)} · Home starts over")
        if state in (S.PLAYING, S.PAUSED) and not self._play_recorded:
            self._record_play()
        elif state is S.PAUSED:
            self._save_history()
        elif state is S.ENDED:
            a, b = self._ab
            if a is not None and b is not None:  # B was at (or past) the end: keep repeating
                QTimer.singleShot(0, lambda: self.seek_to(a))
                return
            self._record_finished()
            if self._queue and self._queue_index < len(self._queue) - 1:
                QTimer.singleShot(0, self.next_in_queue)
        if state in TRACK_STATES:
            self._maybe_apply_tracks()
        if state is S.READY and self._media_name:
            self._show_message("info", self._media_name, "Stopped. Press Space to play again.")
            self.controls.set_position(0, self._duration_ms)
        if state is not S.PLAYING:
            self._show_controls()
        self.state_changed.emit(state)

    def _apply_media_info(self, info: MediaInfo) -> None:
        self._duration_ms = info.duration_ms
        self._update_marks()
        if (
            info.video_codec
            and info.duration_ms
            and self._current_uri
            and not is_network_uri(self._current_uri)
        ):
            self._set_preview(self._current_uri)
        self.media_info_changed.emit()
        self.controls.set_position(self._controller.status().position_ms, info.duration_ms)
        if info.video_codec is None and info.audio_codec is not None:
            self._is_audio_only = True
            self._show_message("music", self._media_name, f"Audio · {info.audio_codec}")
            self._message_action.hide()
        elif self._state in (S.PLAYING, S.PAUSED, S.BUFFERING, S.LOADING):
            self._stage.setCurrentWidget(self.video)
        self._apply_state(self._state)  # also applies track preferences once tracks are known

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
        if status.state is S.PLAYING:
            self._check_ab_loop(status.position_ms)
        self._ticks += 1
        if status.state is S.PLAYING and self._ticks % STATUS_REFRESH_TICKS == 0:
            self._show_engine_status()
        if status.state is S.PLAYING and self._ticks % (SAVE_INTERVAL_MS // POSITION_REFRESH_MS) == 0:
            self._save_history()

    # --------------------------------------------------------- lifecycle
    def shutdown(self) -> None:
        """Close the engine. Must run while the window (and the video surface) still exists."""
        self._save_history()
        self._closing = True
        if self._sync_dialog is not None:
            self._sync_dialog.close()
        self._position_timer.stop()
        self._cursor_timer.stop()
        self._popup.hide()
        if self._preview is not None:
            self._preview.shutdown()
        self._controller.shutdown()
        if self._engine_thread is not None:
            self._engine_thread.join(timeout=10)
