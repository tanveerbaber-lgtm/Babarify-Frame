"""Local logs and crash records (M10). Nothing is ever sent anywhere.

* ``app.log``: the app's log (INFO and above), at most three files of 1 MB, oldest dropped.
* ``crash.log``: Python tracebacks of unhandled errors, and native crash stacks written by
  ``faulthandler`` (the only record an access violation leaves). Kept to the last 512 KB.
Folder: ``%LOCALAPPDATA%\\Babarify\\Frame\\logs`` (BABARIFY_LOG_DIR overrides it). Logs can
contain file names and paths of media you played; the privacy notice says so, and the folder
can be deleted at any time.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import TextIO

MAX_CRASH_BYTES = 512 * 1024
_crash_file: TextIO | None = None  # kept open: faulthandler writes to it from a crashing process


def log_dir() -> Path:
    override = os.environ.get("BABARIFY_LOG_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Babarify" / "Frame" / "logs"


def _trim(path: Path, limit: int) -> None:
    try:
        if path.stat().st_size > limit:
            data = path.read_bytes()[-limit // 2 :]
            path.write_bytes(b"[older entries removed]\n" + data)
    except OSError:
        pass


def setup(version: str) -> Path | None:
    """Start file logging and crash recording; returns the folder, or None if it is not writable."""
    global _crash_file
    folder = log_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        logging.basicConfig(level=logging.INFO)
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:  # a console (development); a windowed release has none
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(console)
    crash = folder / "crash.log"
    _trim(crash, MAX_CRASH_BYTES)
    _crash_file = crash.open("a", encoding="utf-8")
    _crash_file.write(f"--- start {time.strftime('%Y-%m-%d %H:%M:%S')} version {version} ---\n")
    _crash_file.flush()
    faulthandler.enable(_crash_file)
    sys.excepthook = _excepthook
    logging.getLogger(__name__).info("Babarify Media Player %s started", version)
    return folder


def _excepthook(kind: type[BaseException], value: BaseException, tb: TracebackType | None) -> None:
    text = "".join(traceback.format_exception(kind, value, tb))
    logging.getLogger("babarify_frame.crash").error("unhandled error:\n%s", text)
    if _crash_file is not None:
        _crash_file.write(f"--- unhandled error {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}")
        _crash_file.flush()
