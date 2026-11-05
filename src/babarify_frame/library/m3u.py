"""M3U playlist files, which most media players can read and write."""

from __future__ import annotations

import os
from pathlib import Path


def parse(text: str, folder: Path) -> list[str]:
    """The files a playlist names. A relative path means relative to the playlist's own folder."""
    paths = []
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        is_absolute = "://" in line or os.path.isabs(line)
        paths.append(line if is_absolute else str(folder / line))
    return paths


def render(items: list[tuple[str, str]]) -> str:
    """The text of a playlist, from (path, title) pairs."""
    lines = ["#EXTM3U"]
    for path, title in items:
        lines += [f"#EXTINF:-1,{' '.join(title.split())}", path]
    return "\n".join(lines) + "\n"


def read(path: Path) -> list[str]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")  # Plain .m3u files from older players often aren't UTF-8.
    return parse(text, path.parent)
