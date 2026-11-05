"""Media information panel (M8): general facts, tags, every track and the chapters.

Tags and track titles come from the file (or a server) and are untrusted: they are escaped
before display and shortened. The same content can be copied as plain text.
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from babarify_frame.core.models import MediaInfo, TrackInfo, TrackKind
from babarify_frame.core.network import is_network_uri, stream_display_name
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import format_time

MAX_VALUE = 300


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple[tuple[str, str], ...]


def _size(n: int) -> str:
    if n < 1024:
        return f"{n:,} bytes"
    value = float(n)
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            break
    return f"{value:.1f} {unit} ({n:,} bytes)"


def _channels(n: int) -> str:
    return {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(n, f"{n} channels")


def _track_rows(track: TrackInfo) -> tuple[tuple[str, str], ...]:
    rows = [("Codec", track.codec or "unknown")]
    if track.title:
        rows.append(("Title", track.title))
    if track.language and track.language != "und":
        rows.append(("Language", track.language))
    if track.width and track.height:
        rows.append(("Size", f"{track.width} × {track.height}"))  # noqa: RUF001
    if track.frame_rate:
        rows.append(("Frame rate", f"{track.frame_rate:.3f}".rstrip("0").rstrip(".") + " fps"))
    if track.channels:
        rows.append(("Channels", _channels(track.channels)))
    if track.sample_rate:
        rows.append(("Sample rate", f"{track.sample_rate:,} Hz"))
    if track.bitrate:
        rows.append(("Bitrate", f"{track.bitrate // 1000:,} kb/s"))
    if track.selected and track.kind is not TrackKind.VIDEO:
        rows.append(("In use", "yes"))
    return tuple(rows)


def media_sections(info: MediaInfo | None, uri: str) -> list[Section]:
    general: list[tuple[str, str]] = []
    if is_network_uri(uri):
        general += [("Stream", stream_display_name(uri)), ("Address", uri.split("?", 1)[0])]
    elif uri:
        general += [("File", Path(uri).name), ("Folder", str(Path(uri).parent))]
        try:
            size = os.path.getsize(uri)
            general.append(("Size", _size(size)))
            if info is not None and info.duration_ms:
                general.append(("Overall bitrate", f"{size * 8 // info.duration_ms:,} kb/s"))
        except OSError:
            pass
        if Path(uri).suffix:
            general.append(("Container", Path(uri).suffix.lstrip(".").upper()))
    if info is not None:
        general.append(("Duration", format_time(info.duration_ms) if info.duration_ms else "live / unknown"))
    sections = [Section("General", tuple(general))]
    if info is None:
        return sections
    if info.metadata:
        sections.append(Section("Tags", info.metadata))
    for kind, name in (
        (TrackKind.VIDEO, "Video"),
        (TrackKind.AUDIO, "Audio"),
        (TrackKind.SUBTITLE, "Subtitle"),
    ):
        tracks = info.tracks_of(kind)
        for n, track in enumerate(tracks, 1):
            title = name if len(tracks) == 1 else f"{name} {n}"
            sections.append(Section(title, _track_rows(track)))
    if info.chapters:
        sections.append(Section("Chapters", tuple((format_time(c.start_ms), c.label) for c in info.chapters)))
    return sections


def _clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_VALUE else text[: MAX_VALUE - 1] + "…"


def sections_html(sections: list[Section]) -> str:
    parts = []
    for section in sections:
        rows = "".join(
            f"<tr><td style='padding-right:16px;color:{theme.TEXT_MUTED}'>{html.escape(k)}</td>"
            f"<td>{html.escape(_clip(v))}</td></tr>"
            for k, v in section.rows
        )
        parts.append(f"<h3>{html.escape(section.title)}</h3><table>{rows}</table>")
    return "".join(parts)


def sections_text(sections: list[Section]) -> str:
    lines = []
    for section in sections:
        lines.append(section.title)
        lines += [f"  {k}: {_clip(v)}" for k, v in section.rows]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class MediaInfoDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Media information")
        self.resize(560, 620)
        box = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)  # nothing in tags is ever opened
        self.view.setAccessibleName("Media information")
        box.addWidget(self.view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button = QPushButton("Copy")
        buttons.addButton(self.copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self._copy)
        buttons.rejected.connect(self.close)
        box.addWidget(buttons)
        self._text = ""

    def set_media(self, info: MediaInfo | None, uri: str) -> None:
        sections = media_sections(info, uri) if uri else [Section("General", (("Media", "nothing is open"),))]
        self._text = sections_text(sections)
        self.view.setHtml(sections_html(sections))

    @property
    def text(self) -> str:
        return self._text

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text)
        self.copy_button.setText("Copied")
