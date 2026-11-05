"""Library service (M6): owns the database and one background worker for scanning and probing.

The UI never scans or probes on its own thread. Work is queued; the worker scans the requested
folders, then fetches metadata and thumbnails for files that need them. Events are delivered to
listeners on the worker thread (the UI marshals them with ``UiBridge``).

While a video plays, probing pauses between files (``set_playback_active``) so thumbnail
decoding does not compete with playback.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from babarify_frame.core.cover_art import read_embedded_picture
from babarify_frame.core.models import AUDIO_EXTENSIONS
from babarify_frame.library.database import LibraryDatabase, ProbeRecord
from babarify_frame.library.models import path_key
from babarify_frame.library.scanner import ScanSummary, scan_folder
from babarify_frame.playback.media_probe import THUMBNAIL_WIDTH, MediaProbe, ProbeResult

log = logging.getLogger(__name__)

PROBE_PAUSE_PLAYING_S = 0.5
PROBE_BATCH = 25


@dataclass(frozen=True)
class ScanProgress:
    folder: str
    files: int


@dataclass(frozen=True)
class ScanFinished:
    summaries: tuple[ScanSummary, ...]


@dataclass(frozen=True)
class MetadataUpdated:
    count: int  # entries updated since the last event
    remaining: int


@dataclass(frozen=True)
class WorkerIdle:
    pass


LibraryEvent = ScanProgress | ScanFinished | MetadataUpdated | WorkerIdle


def default_thumbnail_dir(db_path: Path | None) -> Path | None:
    return db_path.parent / "thumbnails" if db_path is not None else None


class LibraryService:
    def __init__(
        self,
        db: LibraryDatabase,
        probe_factory: Callable[[], MediaProbe] | None = None,
        thumbnail_dir: Path | None = None,
    ) -> None:
        self.db = db
        self.thumbnail_dir = thumbnail_dir
        self._thumbnail_dir_ready = False
        self._probe_factory = probe_factory
        self._probe: MediaProbe | None = None
        self._probe_failed = False
        self._listeners: list[Callable[[LibraryEvent], None]] = []
        self._queue: queue.Queue[tuple[str, list[int] | None] | None] = queue.Queue()
        self._cancel = threading.Event()
        self._stopping = threading.Event()
        self._playing = threading.Event()
        self._busy = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------- control
    def add_listener(self, listener: Callable[[LibraryEvent], None]) -> None:
        self._listeners.append(listener)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="library-worker", daemon=True)
            self._thread.start()

    def scan(self, folder_ids: list[int] | None = None) -> None:
        """Queue a scan of the given folders (all folders when None), then metadata."""
        self._cancel.clear()
        self._busy.set()
        self._queue.put(("scan", folder_ids))
        self.start()

    def fetch_metadata(self) -> None:
        self._busy.set()
        self._queue.put(("probe", None))
        self.start()

    def cancel(self) -> None:
        """Stop the current scan or probe batch as soon as possible; finished work is kept."""
        self._cancel.set()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def set_playback_active(self, playing: bool) -> None:
        if playing:
            self._playing.set()
        else:
            self._playing.clear()

    def wait_idle(self, timeout: float) -> bool:
        """For tests and tools: wait until queued work is done."""
        deadline = threading.Event()
        timer = threading.Timer(timeout, deadline.set)
        timer.start()
        try:
            while self._busy.is_set() and not deadline.is_set():
                deadline.wait(0.02)
            return not self._busy.is_set()
        finally:
            timer.cancel()

    def shutdown(self, timeout: float = 10) -> None:
        self._stopping.set()
        self.cancel()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        if self._probe is not None:
            self._probe.close()
            self._probe = None

    # ----------------------------------------------------------- worker
    def _emit(self, event: LibraryEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                log.exception("library listener failed")

    def _run(self) -> None:
        while not self._stopping.is_set():
            job = self._queue.get()
            if job is None:  # shutdown
                break
            try:
                kind, arg = job
                if kind == "scan":
                    self._scan(arg)
                    self._probe_pending()
                elif kind == "probe":
                    self._probe_pending()
            except Exception:
                log.exception("library job failed")
            if self._queue.empty():
                self._busy.clear()
                self._cancel.clear()
                self._emit(WorkerIdle())

    def _scan(self, folder_ids: list[int] | None) -> None:
        folders = [f for f in self.db.folders() if folder_ids is None or f.id in folder_ids]
        summaries = []
        for folder in folders:
            if self._cancel.is_set():
                break

            def progress(files: int, folder_path: str = folder.path) -> None:
                self._emit(ScanProgress(folder_path, files))

            summaries.append(scan_folder(self.db, folder, self._cancel, progress))
        self._emit(ScanFinished(tuple(summaries)))

    def _get_probe(self) -> MediaProbe | None:
        if self._probe is None and self._probe_factory is not None and not self._probe_failed:
            try:
                self._probe = self._probe_factory()
            except Exception as exc:  # engine missing: library still works without metadata
                log.warning("media probe unavailable: %s", exc)
                self._probe_failed = True
        return self._probe

    def _probe_pending(self) -> None:
        probe = self._get_probe()
        if probe is None:
            return
        while not self._cancel.is_set() and not self._stopping.is_set():
            pending = self.db.media_to_probe(PROBE_BATCH)
            if not pending:
                break
            done = 0
            for media_id, path in pending:
                if self._cancel.is_set() or self._stopping.is_set():
                    break
                if self._playing.is_set():
                    self._stopping.wait(PROBE_PAUSE_PLAYING_S)
                try:
                    result = probe.probe(path, self._cancel)
                except Exception:
                    log.exception("probe failed for %s", path)
                    result = None
                if self._cancel.is_set():
                    break  # an interrupted probe is not a verdict on the file
                self.db.set_probe_result(media_id, self._record(path, result))
                done += 1
            _total, _missing, remaining = self.db.counts()
            self._emit(MetadataUpdated(done, remaining))
        self._remove_orphan_thumbnails()

    def _record(self, path: str, result: ProbeResult | None) -> ProbeRecord | None:
        if result is None:
            return None
        thumb = self._save_thumbnail(path, result) or self._save_cover(path)
        return ProbeRecord(
            result.duration_ms,
            result.width,
            result.height,
            result.video_codec,
            result.audio_codec,
            thumb,
            result.title,
            result.artist,
            result.album,
            result.year,
        )

    def _save_cover(self, path: str) -> str | None:
        """A song's own picture, as its thumbnail."""
        if self.thumbnail_dir is None or os.path.splitext(path)[1].lower() not in AUDIO_EXTENSIONS:
            return None
        data = read_embedded_picture(path)
        if not data:
            return None
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage  # QImage is safe to use off the GUI thread

        image = QImage.fromData(data)
        if image.isNull():
            return None
        small = image.scaled(
            THUMBNAIL_WIDTH,
            THUMBNAIL_WIDTH,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return self._write_thumbnail(path, small)

    def _save_thumbnail(self, path: str, result: ProbeResult) -> str | None:
        if self.thumbnail_dir is None or not result.thumbnail:
            return None
        from PySide6.QtGui import QImage  # QImage is safe to use off the GUI thread

        w, h = result.thumbnail_width, result.thumbnail_height
        return self._write_thumbnail(path, QImage(result.thumbnail, w, h, w * 4, QImage.Format.Format_RGB32))

    def _write_thumbnail(self, path: str, image: Any) -> str | None:
        assert self.thumbnail_dir is not None
        try:
            stamp = os.stat(path).st_mtime_ns
        except OSError:
            stamp = 0
        name = (
            hashlib.sha1(f"{path_key(path)}|{stamp}".encode(), usedforsecurity=False).hexdigest()[:24]
            + ".jpg"
        )
        if not self._thumbnail_dir_ready:
            self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
            self._thumbnail_dir_ready = True
        if not image.save(str(self.thumbnail_dir / name), quality=82):  # format from the .jpg suffix
            return None
        return name

    def thumbnail_path(self, name: str | None) -> Path | None:
        if not name or self.thumbnail_dir is None:
            return None
        return self.thumbnail_dir / Path(name).name  # never trust a stored name to be a bare file name

    def _remove_orphan_thumbnails(self) -> None:
        if self.thumbnail_dir is None or not self.thumbnail_dir.is_dir():
            return
        used = self.db.thumbnails_in_use()
        for file in self.thumbnail_dir.glob("*.jpg"):
            if file.name not in used:
                with contextlib.suppress(OSError):
                    file.unlink()
