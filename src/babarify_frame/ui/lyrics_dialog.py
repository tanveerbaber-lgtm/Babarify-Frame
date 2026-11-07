"""Shows the lyrics of what's playing and follows along when they have times."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.library import lyrics
from babarify_frame.ui import theme

FOLLOW_MS = 200


class LyricsDialog(QDialog):
    def __init__(self, media_path: str, position: Callable[[], int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Lyrics: {Path(media_path).stem}")
        self.setMinimumSize(460, 560)
        self._media_path = media_path
        self._position = position
        self._lines: list[lyrics.Line] = []
        self._shown = -1
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        self.empty = QLabel("No lyrics for this file yet. Load an .lrc or text file, or type them.")
        self.empty.setWordWrap(True)
        box.addWidget(self.empty)
        self.list = QListWidget()
        self.list.setAccessibleName("Lyrics")
        self.list.setWordWrap(True)
        box.addWidget(self.list, stretch=1)
        row = QHBoxLayout()
        self.load_button = QPushButton("Load a file…")
        self.type_button = QPushButton("Type lyrics…")
        close = QPushButton("Close")
        self.load_button.clicked.connect(self.load_file)
        self.type_button.clicked.connect(self.type_lyrics)
        close.clicked.connect(self.accept)
        row.addWidget(self.load_button)
        row.addWidget(self.type_button)
        row.addStretch(1)
        row.addWidget(close)
        box.addLayout(row)
        self._timer = QTimer(self)
        self._timer.setInterval(FOLLOW_MS)
        self._timer.timeout.connect(self.follow)
        self._show_text(lyrics.load(media_path))
        self._timer.start()

    def _show_text(self, text: str | None) -> None:
        self._lines = lyrics.parse(text or "")
        self._shown = -1
        self.list.clear()
        for line in self._lines:
            item = QListWidgetItem(line.text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.list.addItem(item)
        self.empty.setVisible(not self._lines)
        self.list.setVisible(bool(self._lines))
        self.follow()

    def follow(self) -> None:
        index = lyrics.current_line(self._lines, self._position())
        if index == self._shown:
            return
        for row, bold in ((self._shown, False), (index, True)):
            item = self.list.item(row) if row >= 0 else None
            if item is not None:
                font = item.font()
                font.setBold(bold)
                item.setFont(font)
        self._shown = index
        if index >= 0:
            self.list.setCurrentRow(index)
            self.list.scrollToItem(self.list.item(index), QListWidget.ScrollHint.PositionAtCenter)

    def load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load lyrics", "", "Lyrics (*.lrc *.txt)")
        if not path:
            return
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            QMessageBox.warning(self, "Lyrics", f"That file couldn't be read.\n{exc}")
            return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        self._keep(text)

    def type_lyrics(self) -> None:
        current = lyrics.load(self._media_path) or ""
        text, ok = QInputDialog.getMultiLineText(self, "Type lyrics", "Lyrics:", current)
        if ok:
            self._keep(text)

    def _keep(self, text: str) -> None:
        try:
            lyrics.save(self._media_path, text)
        except OSError as exc:
            QMessageBox.warning(self, "Lyrics", f"The lyrics couldn't be saved.\n{exc}")
            return
        self._show_text(text)

    def done(self, result: int) -> None:
        self._timer.stop()
        super().done(result)
