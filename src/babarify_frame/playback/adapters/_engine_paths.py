"""Locate native engine libraries for development builds.

Search order for each engine:
1. Environment variable (``BABARIFY_VLC_DIR`` / ``BABARIFY_MPV_DIR``).
2. ``<repo>/.engines/vlc/vlc-*/`` and ``<repo>/.engines/mpv/`` (see README).

Packaged releases (M10, ``sys.frozen``) use only ``engines/vlc`` next to the executable: the
environment override is ignored there, so a variable cannot make a release load other DLLs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENGINES = _REPO_ROOT / ".engines"
_added: set[Path] = set()


def bundled_dir() -> Path | None:
    """``engines`` beside the program in a packaged release (the AI worker lives one level down,
    in ``ai``), else None."""
    if not getattr(sys, "frozen", False):
        return None
    folder = Path(sys.executable).resolve().parent
    for base in (folder, folder.parent):
        if (base / "engines").is_dir():
            return base / "engines"
    return folder / "engines"


def find_vlc_dir() -> Path | None:
    bundled = bundled_dir()
    if bundled is not None:
        vlc = bundled / "vlc"
        return vlc if (vlc / "libvlc.dll").is_file() else None
    env = os.environ.get("BABARIFY_VLC_DIR")
    candidates = [Path(env)] if env else sorted((_ENGINES / "vlc").glob("vlc-*"), reverse=True)
    return next((c for c in candidates if (c / "libvlc.dll").is_file()), None)


def find_mpv_dir() -> Path | None:
    if bundled_dir() is not None:
        return None  # releases ship libVLC only (mpv is the opt-in development engine)
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
