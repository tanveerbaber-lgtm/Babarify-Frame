"""Audio and subtitle UI (M5): track labels, the tracks menu and the sync dialog.

Delays use one convention everywhere: milliseconds, positive = later. A subtitle delay of
+500 ms shows each line half a second later; an audio delay of +500 ms plays sound later.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.configuration.preferences import LANGUAGE_ALIASES, LANGUAGES
from babarify_frame.core.models import SUBTITLE_EXTENSIONS, MediaInfo, TrackInfo, TrackKind
from babarify_frame.ui import theme

DELAY_STEP_MS = 50
SUBTITLE_FILTER = (
    "Subtitle files (" + " ".join(f"*{ext}" for ext in sorted(SUBTITLE_EXTENSIONS)) + ");;All files (*)"
)


def language_name(code: str | None) -> str | None:
    if not code:
        return None
    code = code.strip().lower()
    if code in LANGUAGES and code:
        return LANGUAGES[code]
    for key, aliases in LANGUAGE_ALIASES.items():
        if code in aliases:
            return LANGUAGES[key]
    return code


def track_label(track: TrackInfo, index: int) -> str:
    """Human label: title and/or language, falling back to "Track N"; codec in parentheses."""
    language = language_name(track.language)
    title = (track.title or "").strip()
    # libVLC titles are often "Track 1 - [English]"; prefer the language when the title adds nothing.
    if title.lower().startswith("track ") and language:
        title = ""
    parts = [p for p in (title, language) if p]
    if len(parts) == 2 and parts[1].lower() in parts[0].lower():
        parts = parts[:1]
    name = " · ".join(parts) or f"Track {index}"
    return f"{name} ({track.codec})" if track.codec else name


def format_delay(delay_ms: int) -> str:
    return "0 ms" if delay_ms == 0 else f"{delay_ms:+d} ms"


def build_tracks_menu(
    menu: QMenu,
    info: MediaInfo | None,
    *,
    can_load_file: bool,
    on_audio: Callable[[int], None],
    on_subtitle: Callable[[int | None], None],
    on_load_file: Callable[[], None],
    on_sync: Callable[[], object],
) -> None:
    """Fill ``menu`` from the current tracks. Rebuilt each time it opens, so it is never stale."""
    menu.clear()
    audio = list(info.tracks_of(TrackKind.AUDIO)) if info else []
    subs = list(info.tracks_of(TrackKind.SUBTITLE)) if info else []

    menu.addSection("Audio")
    if not audio:
        menu.addAction("No audio tracks").setEnabled(False)
    group = QActionGroup(menu)
    for i, track in enumerate(audio, 1):
        action = menu.addAction(track_label(track, i))
        action.setCheckable(True)
        action.setChecked(track.selected)
        action.triggered.connect(lambda _=False, tid=track.id: on_audio(tid))
        group.addAction(action)

    menu.addSection("Subtitles")
    sub_group = QActionGroup(menu)
    off = menu.addAction("Off")
    off.setCheckable(True)
    off.setChecked(not any(t.selected for t in subs))
    off.setEnabled(info is not None)
    off.triggered.connect(lambda: on_subtitle(None))
    sub_group.addAction(off)
    for i, track in enumerate(subs, 1):
        action = menu.addAction(track_label(track, i))
        action.setCheckable(True)
        action.setChecked(track.selected)
        action.triggered.connect(lambda _=False, tid=track.id: on_subtitle(tid))
        sub_group.addAction(action)
    menu.addSeparator()
    load = menu.addAction("Load subtitle file…")
    load.setEnabled(info is not None and can_load_file)
    load.triggered.connect(on_load_file)
    sync = menu.addAction("Sync and delay…")
    sync.setEnabled(info is not None)
    sync.triggered.connect(on_sync)


class _DelayRow:
    def __init__(self, grid: QGridLayout, row: int, title: str, hint: str, limit_ms: int) -> None:
        label = QLabel(title)
        self.spin = QSpinBox()
        self.spin.setRange(-limit_ms, limit_ms)
        self.spin.setSingleStep(DELAY_STEP_MS)
        self.spin.setSuffix(" ms")
        self.spin.setAccessibleName(f"{title} in milliseconds")
        self.spin.setToolTip(hint)
        self.spin.setMinimumWidth(120)
        label.setBuddy(self.spin)
        self.minus = QPushButton(f"−{DELAY_STEP_MS}")  # noqa: RUF001 (typographic minus intended)
        self.minus.setAccessibleName(f"{title} {DELAY_STEP_MS} ms earlier")
        self.plus = QPushButton(f"+{DELAY_STEP_MS}")
        self.plus.setAccessibleName(f"{title} {DELAY_STEP_MS} ms later")
        self.reset = QPushButton("Reset")
        self.reset.setAccessibleName(f"Reset {title.lower()}")
        self.minus.clicked.connect(lambda: self.spin.stepBy(-1))
        self.plus.clicked.connect(lambda: self.spin.stepBy(1))
        self.reset.clicked.connect(lambda: self.spin.setValue(0))
        for col, widget in enumerate((label, self.spin, self.minus, self.plus, self.reset)):
            grid.addWidget(widget, row, col)
        caption = QLabel(hint)
        caption.setObjectName("caption")
        caption.setWordWrap(True)
        grid.addWidget(caption, row + 1, 1, 1, 4)


class SyncDialog(QDialog):
    """Non-modal: adjust while watching. Values apply immediately and belong to the current file."""

    subtitle_delay_changed = Signal(int)
    audio_delay_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None, limit_ms: int = 60_000) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sync and delay")
        self.setModal(False)
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        box.setSpacing(theme.M)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.S)
        grid.setVerticalSpacing(theme.XS)
        self.subtitle = _DelayRow(
            grid,
            0,
            "Subtitle delay",
            "Positive shows subtitles later; negative shows them earlier. (G / H)",
            limit_ms,
        )
        self.audio = _DelayRow(
            grid, 2, "Audio delay", "Positive plays sound later; negative plays it earlier. (J / K)", limit_ms
        )
        box.addLayout(grid)
        note = QLabel("Delays reset when another file is opened.")
        note.setObjectName("muted")
        box.addWidget(note)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        box.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self.subtitle.spin.valueChanged.connect(self.subtitle_delay_changed)
        self.audio.spin.valueChanged.connect(self.audio_delay_changed)

    def set_delays(self, subtitle_ms: int, audio_ms: int) -> None:
        """Show engine values without echoing them back as changes."""
        for spin, value in ((self.subtitle.spin, subtitle_ms), (self.audio.spin, audio_ms)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def set_enabled_rows(self, enabled: bool) -> None:
        for row in (self.subtitle, self.audio):
            for widget in (row.spin, row.minus, row.plus, row.reset):
                widget.setEnabled(enabled)
