"""Seek-bar hover previews (M8): time, chapter and a small picture above the seek bar.

``SeekPreview`` runs a ``FramePreview`` on one background thread. Only the newest hover
request is decoded (older ones are dropped), and frames are cached per time bucket
(``duration / BUCKETS``), so moving back and forth over the bar does not decode again.
Without a preview source (audio, network streams, previews switched off) the popup still
shows the time and chapter.
"""

from __future__ import annotations

import logging
import threading
import typing
from collections import OrderedDict
from collections.abc import Callable

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from babarify_frame.playback.preview import FramePreview, PreviewFrame
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.widgets import plain_text

log = logging.getLogger(__name__)

BUCKETS = 400  # previews per file at most; 1 s minimum spacing
MAX_CACHED = 400


def frame_pixmap(frame: PreviewFrame) -> QPixmap:
    image = QImage(frame.data, frame.width, frame.height, frame.width * 4, QImage.Format.Format_RGB32)
    return QPixmap.fromImage(image.copy())  # copy: the bytes object is not owned by Qt


class SeekPreview(QObject):
    frame_ready = Signal(int)  # bucket now in the cache

    def __init__(self, source_factory: Callable[[], FramePreview], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._factory = source_factory
        self._bridge = UiBridge(self)
        self._bridge.delivered.connect(self._deliver)
        self._cond = threading.Condition()
        self._generation = 0
        self._open: str | None = None  # path waiting to be opened by the worker
        self._active = False  # the current file is open for previews
        self._wanted = False  # a file is set (requests queue even before it has opened)
        self._request: int | None = None  # bucket waiting to be decoded
        self._step = 1000
        self._cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._stopping = False
        self._thread: threading.Thread | None = None

    # --------------------------------------------------------------- UI thread
    def set_media(self, path: str | None, duration_ms: int | None) -> None:
        """Previews for a local video file, or None to stop."""
        with self._cond:
            self._generation += 1
            self._cache.clear()
            self._request = None
            self._active = False
            self._wanted = bool(path and duration_ms)
            self._open = path if self._wanted else ""
            self._step = max(1000, (duration_ms or 0) // BUCKETS)
            self._cond.notify_all()
        if path and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="seek-preview", daemon=True)
            self._thread.start()

    def bucket_of(self, position_ms: int) -> int:
        return max(0, position_ms) // self._step

    def pixmap(self, bucket: int) -> QPixmap | None:
        return self._cache.get(bucket)

    def request(self, position_ms: int) -> QPixmap | None:
        """The cached picture for this time, or None (then a decode is queued)."""
        bucket = self.bucket_of(position_ms)
        cached = self._cache.get(bucket)
        if cached is not None:
            self._cache.move_to_end(bucket)
            return cached
        with self._cond:
            if self._wanted:
                self._request = bucket
                self._cond.notify_all()
        return None

    @property
    def active(self) -> bool:
        return self._active

    def shutdown(self) -> None:
        with self._cond:
            self._stopping = True
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _deliver(self, payload: object) -> None:
        generation, bucket, frame = typing.cast(tuple[int, int, PreviewFrame | None], payload)
        if generation != self._generation:
            return
        if frame is None:  # opened (or failed to open) with no picture yet
            self._active = bucket >= 0
            return
        self._cache[bucket] = frame_pixmap(frame)
        while len(self._cache) > MAX_CACHED:
            self._cache.popitem(last=False)
        self.frame_ready.emit(bucket)

    # ------------------------------------------------------------- worker thread
    def _run(self) -> None:
        source: FramePreview | None = None
        ready = False  # the worker's own view: did the last open succeed?
        try:
            while True:
                with self._cond:
                    while not self._stopping and self._open is None and self._request is None:
                        self._cond.wait()
                    if self._stopping:
                        return
                    generation, path, bucket, step = self._generation, self._open, self._request, self._step
                    self._open, self._request = None, None
                if path is not None:
                    if source is None and path:
                        source = self._factory()
                    ready = source.open(path) if source is not None and path else False
                    if source is not None and not path:
                        source.close()
                    self._bridge.post((generation, 0 if ready else -1, None))
                if bucket is not None and source is not None and ready:
                    frame = source.frame_at(bucket * step + step // 2)
                    if frame is not None:
                        self._bridge.post((generation, bucket, frame))
        except Exception:  # previews must never take the player down
            log.exception("seek preview failed")
        finally:
            if source is not None:
                source.close()


class PreviewPopup(QFrame):
    """Floating box above the seek bar: optional picture, then time and chapter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("previewPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(
            f"#previewPopup {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; "
            f"border-radius: 6px; }} QLabel {{ color: {theme.TEXT}; background: transparent; }}"
        )
        box = QVBoxLayout(self)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(2)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = QLabel()
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plain_text(self.text)  # chapter titles come from the file
        box.addWidget(self.image)
        box.addWidget(self.text)

    def show_at(self, anchor: QPoint, text: str, pixmap: QPixmap | None) -> None:
        self.text.setText(text)
        self.set_pixmap(pixmap)
        self.adjustSize()
        self.move(anchor.x() - self.width() // 2, anchor.y() - self.height() - 8)
        if not self.isVisible():
            self.show()

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self.image.setVisible(pixmap is not None)
        if pixmap is not None:
            self.image.setPixmap(pixmap)
        self.adjustSize()
