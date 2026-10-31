"""Folder scanner (M6). Runs on the library worker thread, never on the UI thread.

* Only folders the user added are walked; nothing else on the disk is read.
* Hidden and system entries, symbolic links and junctions are skipped (no loops, no surprises).
* Unchanged files (same size and modification time) are not read at all. New or changed files
  get a content key: size plus a SHA-1 of the first and last 64 KiB. Two library entries with
  the same key are reported as duplicates; both stay in the library.
* A cancelled scan changes nothing about files it did not reach; only a completed scan marks
  files that disappeared as unavailable.
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from babarify_frame.core.models import MEDIA_EXTENSIONS
from babarify_frame.library.database import LibraryDatabase, ScanRecord
from babarify_frame.library.models import LibraryFolder, path_key

log = logging.getLogger(__name__)

BATCH_SIZE = 200
HASH_CHUNK = 64 * 1024
_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)


@dataclass(frozen=True)
class ScanSummary:
    folder: str
    files: int  # media files seen
    new_or_changed: int
    missing: int  # marked unavailable by this scan
    cancelled: bool
    available: bool = True  # False if the folder itself could not be read


def content_key(path: str, size: int) -> str | None:
    try:
        digest = hashlib.sha1(usedforsecurity=False)
        with open(path, "rb") as handle:
            digest.update(handle.read(HASH_CHUNK))
            if size > 2 * HASH_CHUNK:
                handle.seek(-HASH_CHUNK, os.SEEK_END)
                digest.update(handle.read(HASH_CHUNK))
        return f"{size}:{digest.hexdigest()}"
    except OSError:
        return None


def _is_hidden(entry: os.DirEntry[str]) -> bool:
    if entry.name.startswith("."):
        return True
    try:
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attrs & _HIDDEN)


def walk_media(root: str, cancel: threading.Event) -> Iterator[os.DirEntry[str]]:
    stack = [root]
    while stack and not cancel.is_set():
        folder = stack.pop()
        try:
            with os.scandir(folder) as entries:
                children = sorted(entries, key=lambda e: e.name.lower())
        except OSError as exc:
            log.info("skipping unreadable folder %s: %s", folder, exc)
            continue
        subfolders = []
        for entry in children:
            if cancel.is_set():
                return
            try:
                if entry.is_symlink() or os.path.isjunction(entry.path) or _is_hidden(entry):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    subfolders.append(entry.path)
                elif os.path.splitext(entry.name)[1].lower() in MEDIA_EXTENSIONS:
                    yield entry
            except OSError:
                continue
        stack.extend(reversed(subfolders))


def scan_folder(
    db: LibraryDatabase,
    folder: LibraryFolder,
    cancel: threading.Event,
    progress: Callable[[int], None] | None = None,
) -> ScanSummary:
    if not os.path.isdir(folder.path):
        db.set_folder_available(folder.id, False)
        return ScanSummary(folder.path, 0, 0, 0, cancelled=False, available=False)
    if not folder.available:
        db.set_folder_available(folder.id, True)
    started = time.time()
    known = db.known_files(folder.id)
    batch: list[ScanRecord] = []
    seen = changed = 0
    for entry in walk_media(folder.path, cancel):
        try:
            info = entry.stat()
        except OSError:
            continue
        seen += 1
        previous = known.get(path_key(entry.path))
        if previous is not None and previous[:2] == (info.st_size, info.st_mtime):
            key = previous[2]
        else:
            key = content_key(entry.path, info.st_size)
            changed += 1
        batch.append(ScanRecord(entry.path, folder.id, info.st_size, info.st_mtime, key))
        if len(batch) >= BATCH_SIZE:
            db.upsert_media(batch, started)
            batch.clear()
            if progress is not None:
                progress(seen)
    if batch:
        db.upsert_media(batch, started)
    if progress is not None:
        progress(seen)
    cancelled = cancel.is_set()
    missing = 0 if cancelled else db.mark_missing(folder.id, started)
    return ScanSummary(folder.path, seen, changed, missing, cancelled)
