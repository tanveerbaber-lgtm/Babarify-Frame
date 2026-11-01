"""Bookmarks dialog (M8): the current file's bookmarks; jump, rename, delete.

Bookmarks are stored locally in the library database, per file (like history). They are
the user's own notes, so they are kept when history is cleared or switched off.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.library.models import Bookmark
from babarify_frame.ui.widgets import format_time


def bookmark_text(bookmark: Bookmark) -> str:
    time = format_time(bookmark.position_ms)
    return f"{time}  {bookmark.label}" if bookmark.label else time


class BookmarksDialog(QDialog):
    jump_requested = Signal(int)  # position ms
    add_requested = Signal()
    rename_requested = Signal(int, str)  # id, label
    delete_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bookmarks")
        self.resize(420, 420)
        box = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName("muted")
        self.title.setWordWrap(True)
        box.addWidget(self.title)
        self.list = QListWidget()
        self.list.setAccessibleName("Bookmarks")
        self.list.itemDoubleClicked.connect(self._jump)
        self.list.currentRowChanged.connect(lambda _row: self._update_buttons())
        box.addWidget(self.list, stretch=1)
        self.empty = QLabel("No bookmarks yet. Press Ctrl+B while playing to add one.")
        self.empty.setObjectName("muted")
        box.addWidget(self.empty)
        row = QHBoxLayout()
        self.add_button = QPushButton("Add at current time")
        self.add_button.clicked.connect(self.add_requested)
        self.jump_button = QPushButton("Go to")
        self.jump_button.clicked.connect(lambda: self._jump(self.list.currentItem()))
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self._rename)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete)
        for button in (self.add_button, self.jump_button, self.rename_button, self.delete_button):
            row.addWidget(button)
        box.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        box.addWidget(buttons)
        self._bookmarks: list[Bookmark] = []
        self.set_bookmarks("", [], can_add=False)

    def set_bookmarks(self, media_name: str, bookmarks: list[Bookmark], *, can_add: bool) -> None:
        current = self.list.currentRow()
        self._bookmarks = list(bookmarks)
        self.title.setText(media_name or "Nothing is open")
        self.list.clear()
        for bookmark in bookmarks:
            item = QListWidgetItem(bookmark_text(bookmark))
            item.setData(Qt.ItemDataRole.UserRole, bookmark.id)
            self.list.addItem(item)
        if bookmarks:
            self.list.setCurrentRow(max(0, min(current, len(bookmarks) - 1)))
        self.empty.setVisible(not bookmarks)
        self.add_button.setEnabled(can_add)
        self._update_buttons()

    def _selected(self) -> Bookmark | None:
        row = self.list.currentRow()
        return self._bookmarks[row] if 0 <= row < len(self._bookmarks) else None

    def _update_buttons(self) -> None:
        has = self._selected() is not None
        for button in (self.jump_button, self.rename_button, self.delete_button):
            button.setEnabled(has)

    def _jump(self, _item: QListWidgetItem | None = None) -> None:
        bookmark = self._selected()
        if bookmark is not None:
            self.jump_requested.emit(bookmark.position_ms)

    def _rename(self) -> None:
        bookmark = self._selected()
        if bookmark is None:
            return
        label, ok = QInputDialog.getText(self, "Rename bookmark", "Name", text=bookmark.label)
        if ok:
            self.rename_requested.emit(bookmark.id, label)

    def _delete(self) -> None:
        bookmark = self._selected()
        if bookmark is not None:
            self.delete_requested.emit(bookmark.id)
