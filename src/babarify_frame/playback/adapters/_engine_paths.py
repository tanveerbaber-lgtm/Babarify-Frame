"""Locate native engine libraries for development builds.

Search order for each engine:
1. Environment variable (``BABARIFY_VLC_DIR`` / ``BABARIFY_MPV_DIR``).
2. ``<repo>/.engines/vlc/vlc-*/`` and ``<repo>/.engines/mpv/`` (see README).

Packaged releases will bundle engines next to the executable (M10).
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENGINES = _REPO_ROOT / ".engines"
_added: set[Path] = set()


def find_vlc_dir() -> Path | None:
    env = os.environ.get("BABARIFY_VLC_DIR")
    candidates = [Path(env)] if env else sorted((_ENGINES / "vlc").glob("vlc-*"), reverse=True)
    return next((c for c in candidates if (c / "libvlc.dll").is_file()), None)


def find_mpv_dir() -> Path | None:
    env = os.environ.get("BABARIFY_MPV_DIR")
    candidates = [Path(env)] if env else [_ENGINES / "mpv"]
    return next((c for c in candidates if (c / "libmpv-2.dll").is_file()), None)


def add_dll_dir(path: Path) -> None:
    """Make a DLL directory visible to ctypes for this process (Windows)."""
    path = path.resolve()
    if path in _added:
        return
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(path))
    os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")
    _added.add(path)
