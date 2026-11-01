"""Generated subtitles (M9): cues from recognised speech, SRT output and where files live.

Whisper segments can be up to 30 s long, so cues are rebuilt from word timings: a cue ends at
a sentence end, before it would exceed MAX_CUE_CHARS or MAX_CUE_MS, or at a pause longer than
SPLIT_PAUSE_MS. Text is wrapped onto at most two lines.

Files are named ``<name>.<language>.machine-generated.srt`` (the label shows in the track
list) and kept under ``<config>\\Babarify\\Frame\\subtitles``: never next to the user's media.
"""

from __future__ import annotations

import hashlib
import os
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from babarify_frame.library.models import path_key

MAX_CUE_CHARS = 84  # two lines of 42, the usual subtitle limit
MAX_CUE_MS = 7_000
SPLIT_PAUSE_MS = 700
LINE_CHARS = 42
MIN_CUE_MS = 700
MACHINE_TAG = "machine-generated"


@dataclass(frozen=True)
class Word:
    start_ms: int
    end_ms: int
    text: str  # as recognised, with its leading space


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


def build_cues(words: Iterable[Word]) -> list[Cue]:
    cues: list[Cue] = []
    current: list[Word] = []

    def flush() -> None:
        if current:
            text = " ".join("".join(w.text for w in current).split())
            if text:
                cues.append(
                    Cue(current[0].start_ms, max(current[-1].end_ms, current[0].start_ms + MIN_CUE_MS), text)
                )
            current.clear()

    for word in words:
        if current:
            length = len("".join(w.text for w in current) + word.text.rstrip())
            too_long = length > MAX_CUE_CHARS or word.end_ms - current[0].start_ms > MAX_CUE_MS
            if too_long or word.start_ms - current[-1].end_ms > SPLIT_PAUSE_MS:
                flush()
        current.append(word)
        if word.text.rstrip().endswith((".", "?", "!")) and len("".join(w.text for w in current)) > 20:
            flush()
    flush()
    # Never overlap: a cue ends before the next one starts.
    for i in range(len(cues) - 1):
        if cues[i].end_ms > cues[i + 1].start_ms:
            cues[i] = Cue(cues[i].start_ms, max(cues[i].start_ms + 1, cues[i + 1].start_ms), cues[i].text)
    return cues


def _timestamp(ms: int) -> str:
    ms = max(0, ms)
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def to_srt(cues: Sequence[Cue]) -> str:
    blocks = []
    for n, cue in enumerate(cues, 1):
        lines = textwrap.wrap(cue.text, LINE_CHARS) or [""]
        if len(lines) > 2:  # keep two lines: the second takes the rest
            lines = [lines[0], " ".join(lines[1:])]
        blocks.append(f"{n}\n{_timestamp(cue.start_ms)} --> {_timestamp(cue.end_ms)}\n" + "\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def generated_dir() -> Path:
    base = os.environ.get("BABARIFY_CONFIG_DIR") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Babarify" / "Frame" / "subtitles"


def subtitle_path(media: str, language: str) -> Path:
    """Where the generated subtitle for a file and language goes (one folder per file)."""
    folder = hashlib.sha1(path_key(media).encode("utf-8")).hexdigest()[:16]
    stem = Path(media).stem[:80] or "media"
    safe = "".join(c if c.isalnum() or c in " -_()" else "_" for c in stem).strip() or "media"
    lang = "".join(c for c in language.lower() if c.isalpha())[:8] or "und"
    return generated_dir() / folder / f"{safe}.{lang}.{MACHINE_TAG}.srt"
