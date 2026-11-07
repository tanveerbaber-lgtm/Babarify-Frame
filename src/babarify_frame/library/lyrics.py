"""Lyrics the person supplies: saved, or an .lrc file beside the media file. Nothing is looked up online."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from babarify_frame.configuration.preferences import default_settings_path

_TAG = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_METADATA = re.compile(r"^\[[a-zA-Z]+:.*\]$")


@dataclass(frozen=True)
class Line:
    time_ms: int | None  # None when the lyrics have no timing
    text: str


def parse(text: str) -> list[Line]:
    """Lines in time order when any line has a time, otherwise as written."""
    timed: list[Line] = []
    plain: list[Line] = []
    for raw in text.lstrip("﻿").splitlines():
        line = raw.strip()
        if _METADATA.match(line):
            continue
        tags = list(_TAG.finditer(line))
        words = _TAG.sub("", line).strip()
        if tags:
            timed.extend(Line(_milliseconds(tag), words) for tag in tags)
        else:
            plain.append(Line(None, words))
    if timed:
        return sorted(timed, key=lambda item: item.time_ms or 0)
    while plain and not plain[0].text:
        plain.pop(0)
    while plain and not plain[-1].text:
        plain.pop()
    return plain


def current_line(lines: list[Line], position_ms: int) -> int:
    """The line being sung; -1 before the first line, or when the lyrics have no timing."""
    found = -1
    for index, line in enumerate(lines):
        if line.time_ms is None or line.time_ms > position_ms:
            break
        found = index
    return found


def load(media_path: str, folder: Path | None = None) -> str | None:
    """The saved lyrics, otherwise an .lrc file with the same name beside the media file."""
    saved = _saved_path(media_path, folder)
    candidates = [saved]
    if "://" not in media_path:
        candidates.append(Path(media_path).with_suffix(".lrc"))
    for path in candidates:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")
    return None


def save(media_path: str, text: str, folder: Path | None = None) -> None:
    path = _saved_path(media_path, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _saved_path(media_path: str, folder: Path | None) -> Path:
    base = folder or default_settings_path().parent / "lyrics"
    return base / f"{hashlib.sha256(media_path.casefold().encode()).hexdigest()[:32]}.lrc"


def _milliseconds(tag: re.Match[str]) -> int:
    fraction = (tag.group(3) or "0").ljust(3, "0")
    return (int(tag.group(1)) * 60 + int(tag.group(2))) * 1000 + int(fraction)
