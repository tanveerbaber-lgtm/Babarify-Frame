"""Library page (M6): folders you choose, search and sort, playlists.

All database work here is short (one query); scanning and metadata run on the library worker
(``LibraryService``) and report back through ``UiBridge``. Nothing on disk is ever deleted from
this page: "Remove" removes library records only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.library.database import LibraryError
from babarify_frame.library.models import MediaEntry, PlaylistItem, SortOrder
from babarify_frame.library.music import GroupKind
from babarify_frame.library.service import (
    LibraryEvent,
    LibraryService,
    MetadataUpdated,
    ScanFinished,
    ScanProgress,
    WorkerIdle,
)
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.library_view import CARD, LibraryDelegate, LibraryModel
from babarify_frame.ui.music_panel import MusicPanel

SORT_LABELS = {
    SortOrder.NAME: "Name",
    SortOrder.DATE_ADDED: "Date added",
    SortOrder.RECENTLY_PLAYED: "Recently played",
    SortOrder.DURATION: "Longest first",
    SortOrder.SIZE: "Largest first",
}
SEARCH_DELAY_MS = 200
REFRESH_DELAY_MS = 500  # metadata arrives in batches; re-query the grid at most twice a second


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def reveal_in_explorer(path: str) -> None:
    """Show a file in Windows Explorer (local, user-initiated)."""
    if sys.platform == "win32" and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


class FoldersDialog(QDialog):
    """Choose which folders are scanned. Removing a folder keeps the files and the history."""

    def __init__(self, service: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Library folders")
        self.setMinimumWidth(560)
        self._service = service
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        box.setSpacing(theme.M)
        box.addWidget(
            _label(
                "Only these folders (and the folders inside them) are scanned. Removing a folder removes "
                "its entries from the library; the files themselves are never touched.",
                "muted",
            )
        )
        self.list = QListWidget()
        self.list.setAccessibleName("Library folders")
        box.addWidget(self.list)
        row = QHBoxLayout()
        self.add_button = QPushButton("Add folder…")
        self.remove_button = QPushButton("Remove")
        self.remove_button.setAccessibleName("Remove selected folder")
        close = QPushButton("Close")
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        close.clicked.connect(self.accept)
        for button in (self.add_button, self.remove_button):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(close)
        box.addLayout(row)
        self.list.currentRowChanged.connect(lambda r: self.remove_button.setEnabled(r >= 0))
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for folder in self._service.db.folders():
            item = QListWidgetItem(folder.path + ("" if folder.available else "   (not reachable)"))
            item.setData(Qt.ItemDataRole.UserRole, folder.id)
            self.list.addItem(item)
        self.remove_button.setEnabled(False)

    def add_folder(self, path: str) -> bool:
        try:
            folder = self._service.db.add_folder(path)
        except LibraryError as exc:
            QMessageBox.information(self, "Library folders", str(exc))
            return False
        self.refresh()
        self._service.scan([folder.id])
        return True

    def _add(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add a folder to the library")
        if path:
            self.add_folder(path)

    def _remove(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self._service.cancel()
        self._service.db.remove_folder(int(item.data(Qt.ItemDataRole.UserRole)))
        self.refresh()


AUTOMATIC_LISTS = ("Favourites", "Recently played", "Most played", "Recently added")


class PlaylistsPanel(QWidget):
    play_requested = Signal(list, int)  # paths, start index

    def __init__(self, service: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.L)

        left = QVBoxLayout()
        self.automatic = QListWidget()
        self.automatic.setAccessibleName("Automatic playlists")
        self.automatic.setMaximumWidth(280)
        self.automatic.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.automatic.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for name in AUTOMATIC_LISTS:
            self.automatic.addItem(name)
        left.addWidget(self.automatic)
        left.addWidget(_label("Your playlists", "caption"))
        self.playlists = QListWidget()
        self.playlists.setAccessibleName("Playlists")
        self.playlists.setMaximumWidth(280)
        left.addWidget(self.playlists, stretch=1)
        buttons = QHBoxLayout()
        self.new_button = QPushButton("New…")
        self.rename_button = QPushButton("Rename…")
        self.delete_button = QPushButton("Delete")
        for button in (self.new_button, self.rename_button, self.delete_button):
            buttons.addWidget(button)
        left.addLayout(buttons)
        row.addLayout(left)

        right = QVBoxLayout()
        self.items = QListWidget()
        self.items.setAccessibleName("Playlist items")
        self.items.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        right.addWidget(self.items, stretch=1)
        item_buttons = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("primary")
        self.up_button = QPushButton("Move up")
        self.down_button = QPushButton("Move down")
        self.remove_button = QPushButton("Remove from playlist")
        for button in (self.play_button, self.up_button, self.down_button, self.remove_button):
            item_buttons.addWidget(button)
        item_buttons.addStretch(1)
        right.addLayout(item_buttons)
        self.hint = _label("Add files from the Media tab: right-click a file → Add to playlist.", "caption")
        right.addWidget(self.hint)
        row.addLayout(right, stretch=1)

        self.new_button.clicked.connect(self.new_playlist)
        self.rename_button.clicked.connect(self._rename)
        self.delete_button.clicked.connect(self._delete)
        self.play_button.clicked.connect(self._play)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button.clicked.connect(lambda: self._move(1))
        self.remove_button.clicked.connect(self._remove_item)
        self.playlists.currentRowChanged.connect(self._playlist_chosen)
        self.automatic.currentRowChanged.connect(self._automatic_chosen)
        self.items.itemActivated.connect(lambda _i: self._play())
        self.refresh()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Only now does a row know its height, because the app's style has been applied.
        frame = self.automatic.frameWidth() * 2
        self.automatic.setFixedHeight(self.automatic.sizeHintForRow(0) * len(AUTOMATIC_LISTS) + frame + 2)
        self.automatic.scrollToTop()

    @property
    def current_automatic(self) -> str | None:
        item = self.automatic.currentItem()
        return item.text() if item is not None and item.isSelected() else None

    def _playlist_chosen(self, row: int) -> None:
        if row >= 0:
            self.automatic.blockSignals(True)
            self.automatic.clearSelection()
            self.automatic.setCurrentRow(-1)
            self.automatic.blockSignals(False)
        self._show_items()

    def _automatic_chosen(self, row: int) -> None:
        if row >= 0:
            self.playlists.blockSignals(True)
            self.playlists.clearSelection()
            self.playlists.setCurrentRow(-1)
            self.playlists.blockSignals(False)
        self._show_items()

    def _automatic_items(self, name: str) -> list[PlaylistItem]:
        db = self._service.db
        return {
            "Favourites": db.favourites,
            "Recently played": db.recently_played_songs,
            "Most played": db.most_played_songs,
            "Recently added": db.recently_added_songs,
        }[name]()

    @property
    def current_playlist(self) -> int | None:
        item = self.playlists.currentItem()
        return int(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def refresh(self, select: int | None = None) -> None:
        current = select if select is not None else self.current_playlist
        automatic_row = self.automatic.currentRow() if self.current_automatic and select is None else -1
        self.playlists.blockSignals(True)
        self.playlists.clear()
        for playlist in self._service.db.playlists():
            item = QListWidgetItem(f"{playlist.name}  ({playlist.item_count})")
            item.setData(Qt.ItemDataRole.UserRole, playlist.id)
            self.playlists.addItem(item)
            if playlist.id == current:
                self.playlists.setCurrentItem(item)
        if automatic_row < 0 and self.playlists.currentRow() < 0 and self.playlists.count():
            self.playlists.setCurrentRow(0)
        self.playlists.blockSignals(False)
        self.automatic.blockSignals(True)
        self.automatic.setCurrentRow(automatic_row)
        if automatic_row < 0:
            self.automatic.clearSelection()
        elif (item := self.automatic.item(automatic_row)) is not None:
            item.setSelected(True)
        self.automatic.blockSignals(False)
        self._show_items()

    def _show_items(self, select_row: int | None = None) -> None:
        self.items.clear()
        pid = self.current_playlist
        automatic = self.current_automatic
        for button in (self.rename_button, self.delete_button):
            button.setEnabled(pid is not None and automatic is None)
        shown: list[PlaylistItem] = []
        if automatic is not None:
            shown = self._automatic_items(automatic)
        elif pid is not None:
            shown = self._service.db.playlist_items(pid)
        if shown or automatic is not None or pid is not None:
            for entry in shown:
                text = entry.title if entry.available else f"{entry.title}   (not found)"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, entry.path)
                item.setToolTip(entry.path)
                if not entry.available:
                    item.setForeground(Qt.GlobalColor.gray)
                self.items.addItem(item)
        if select_row is not None and self.items.count():
            self.items.setCurrentRow(max(0, min(select_row, self.items.count() - 1)))
        has_items = self.items.count() > 0
        self.play_button.setEnabled(has_items)
        for button in (self.up_button, self.down_button):
            button.setEnabled(has_items and automatic is None)
        self.remove_button.setEnabled(has_items and automatic in (None, "Favourites"))
        self.remove_button.setText("Remove from favourites" if automatic else "Remove from playlist")
        if automatic == "Favourites":
            self.hint.setText("Press the heart while a song plays, or right-click a song, to add it here.")
        elif automatic:
            self.hint.setText("This list fills itself in from what you play and add.")
        else:
            self.hint.setText("Add files from the Media tab: right-click a file → Add to playlist.")

    def new_playlist(self, name: str | None = None) -> int | None:
        if name is None:
            name, ok = QInputDialog.getText(self, "New playlist", "Name:")
            if not ok:
                return None
        try:
            playlist = self._service.db.create_playlist(name)
        except LibraryError as exc:
            QMessageBox.information(self, "Playlists", str(exc))
            return None
        self.refresh(select=playlist.id)
        return playlist.id

    def _rename(self) -> None:
        pid = self.current_playlist
        if pid is None:
            return
        name, ok = QInputDialog.getText(self, "Rename playlist", "Name:")
        if ok:
            try:
                self._service.db.rename_playlist(pid, name)
            except LibraryError as exc:
                QMessageBox.information(self, "Playlists", str(exc))
            self.refresh()

    def _delete(self) -> None:
        pid = self.current_playlist
        if pid is None:
            return
        answer = QMessageBox.question(
            self, "Delete playlist", "Delete this playlist? The files themselves are not affected."
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._service.db.delete_playlist(pid)
            self.refresh()

    def _play(self) -> None:
        paths = [
            str(self.items.item(i).data(Qt.ItemDataRole.UserRole + 1)) for i in range(self.items.count())
        ]
        if paths:
            self.play_requested.emit(paths, max(0, self.items.currentRow()))

    def _move(self, delta: int) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        row = self.items.currentRow()
        self._service.db.move_playlist_item(int(item.data(Qt.ItemDataRole.UserRole)), delta)
        self._show_items(select_row=row + delta)

    def _remove_item(self) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        row = self.items.currentRow()
        if self.current_automatic == "Favourites":
            self._service.db.set_favourite(str(item.data(Qt.ItemDataRole.UserRole + 1)), "", False)
        else:
            self._service.db.remove_playlist_item(int(item.data(Qt.ItemDataRole.UserRole)))
        self.refresh()
        self._show_items(select_row=row)


class LibraryPage(QWidget):
    play_requested = Signal(str)
    play_list_requested = Signal(list, int)
    shuffle_requested = Signal(list)
    status_changed = Signal(str)
    sort_changed = Signal(str)

    def __init__(self, service: LibraryService, sort: str = "name", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self._service = service
        self._bridge = UiBridge(self)
        self._bridge.delivered.connect(self._on_library_event)
        service.add_listener(self._bridge.post)
        self._scanned = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.XXL, theme.XL, theme.XXL, theme.L)
        outer.setSpacing(theme.M)
        header = QHBoxLayout()
        header.addWidget(_label("Library", "title"))
        header.addStretch(1)
        self.folders_button = QPushButton("Folders…")
        self.folders_button.setAccessibleName("Choose library folders")
        self.scan_button = QPushButton("Rescan")
        self.scan_button.setAccessibleName("Rescan library folders")
        self.cancel_button = QPushButton("Stop")
        self.cancel_button.setAccessibleName("Stop scanning")
        self.cancel_button.hide()
        for button in (self.folders_button, self.scan_button, self.cancel_button):
            header.addWidget(button)
        outer.addLayout(header)

        self.tabs = QTabBar()
        for name in ("Media", "Songs", "Albums", "Artists", "Playlists"):
            self.tabs.addTab(name)
        self.tabs.setAccessibleName("Library sections")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        outer.addWidget(self.tabs)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, stretch=1)

        media = QWidget()
        media_box = QVBoxLayout(media)
        media_box.setContentsMargins(0, 0, 0, 0)
        media_box.setSpacing(theme.M)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search names and folders")
        self.search.setAccessibleName("Search library")
        self.search.setClearButtonEnabled(True)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Sort library")
        for order, text in SORT_LABELS.items():
            self.sort.addItem(text, order.value)
        index = self.sort.findData(sort)
        self.sort.setCurrentIndex(max(0, index))
        self.remove_missing_button = QPushButton("Remove unavailable")
        self.remove_missing_button.setToolTip("Remove entries whose files can no longer be found")
        self.remove_missing_button.hide()
        tools.addWidget(self.search, stretch=1)
        tools.addWidget(self.sort)
        tools.addWidget(self.remove_missing_button)
        media_box.addLayout(tools)
        self.summary = _label("", "caption")
        media_box.addWidget(self.summary)

        self.view_stack = QStackedWidget()
        self.empty = QWidget()
        empty_box = QVBoxLayout(self.empty)
        empty_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = _label("Build your library", "subtitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_body = _label(
            "Choose the folders that hold your videos and music. Only those folders are scanned, "
            "and everything stays on this PC.",
            "muted",
        )
        self.empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_body.setMaximumWidth(520)
        self.empty_action = QPushButton("Add folder…")
        self.empty_action.setObjectName("primary")
        empty_box.addWidget(self.empty_title, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_box.addWidget(self.empty_body, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_box.addWidget(self.empty_action, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.view = QListView()
        self.view.setAccessibleName("Library media")
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setUniformItemSizes(True)
        self.view.setGridSize(CARD + QSize(theme.S, theme.S))
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setMouseTracking(True)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.setFrameShape(QListView.Shape.NoFrame)
        self.model = LibraryModel(service.thumbnail_path, service.db.duplicates_of, self)
        self.view.setModel(self.model)
        self.view.setItemDelegate(LibraryDelegate(self.view))
        self.view_stack.addWidget(self.empty)
        self.view_stack.addWidget(self.view)
        media_box.addWidget(self.view_stack, stretch=1)
        self.stack.addWidget(media)

        self.songs_panel = self._music_panel(None)
        self.albums_panel = self._music_panel(GroupKind.ALBUM)
        self.artists_panel = self._music_panel(GroupKind.ARTIST)
        self.playlists = PlaylistsPanel(service)
        self.stack.addWidget(self.playlists)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self.refresh)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self.sort.currentIndexChanged.connect(self._sort_changed)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.folders_button.clicked.connect(self.manage_folders)
        self.empty_action.clicked.connect(self.manage_folders)
        self.scan_button.clicked.connect(lambda: self.rescan())
        self.cancel_button.clicked.connect(self._service.cancel)
        self.remove_missing_button.clicked.connect(self.remove_unavailable)
        self.view.activated.connect(lambda index: self._play_rows([index.row()]))
        self.view.customContextMenuRequested.connect(self._context_menu)
        self.playlists.play_requested.connect(self.play_list_requested)
        self.refresh()

    # ---------------------------------------------------------- music
    def _music_panel(self, kind: GroupKind | None) -> MusicPanel:
        panel = MusicPanel(self._service, kind, self._fill_playlist_menu, reveal_in_explorer)
        panel.play_requested.connect(self.play_list_requested)
        panel.shuffle_requested.connect(self.shuffle_requested)
        panel.status_changed.connect(self.status_changed)
        self.stack.addWidget(panel)
        return panel

    def _music_panels(self) -> tuple[MusicPanel, MusicPanel, MusicPanel]:
        return (self.songs_panel, self.albums_panel, self.artists_panel)

    def _tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.refresh_current_tab()

    def refresh_current_tab(self) -> None:
        """Only what's on show: Songs, Albums and Artists read every song in the library."""
        current = self.stack.currentWidget()
        if isinstance(current, MusicPanel):
            current.refresh()
        elif current is self.playlists:
            self.playlists.refresh()

    def _fill_playlist_menu(self, menu: QMenu, entries: list[MediaEntry]) -> None:
        for playlist in self._service.db.playlists():
            action = menu.addAction(playlist.name)
            action.triggered.connect(lambda _=False, pid=playlist.id: self.add_to_playlist(pid, entries))
        menu.addSeparator()
        new = menu.addAction("New playlist…")
        new.triggered.connect(lambda: self._add_to_new_playlist(entries))

    # ----------------------------------------------------------- data
    @property
    def sort_order(self) -> SortOrder:
        return SortOrder(self.sort.currentData())

    def refresh(self) -> None:
        db = self._service.db
        entries = db.media(self.search.text().strip(), self.sort_order)
        self.model.set_entries(entries)
        total, missing, pending = db.counts()
        has_folders = bool(db.folders())
        self.view_stack.setCurrentWidget(self.view if total or self.search.text() else self.empty)
        if has_folders and not total:
            self.empty_title.setText("No media found yet")
            self.empty_body.setText(
                "The library folders hold no video or audio files that Babarify Media Player recognises, "
                "or the scan has not finished. Add another folder or rescan."
            )
        self.remove_missing_button.setVisible(missing > 0)
        self.remove_missing_button.setText(f"Remove unavailable ({missing})")
        self.scan_button.setEnabled(has_folders)
        parts = [f"{len(entries)} of {total} files" if self.search.text().strip() else f"{total} files"]
        if missing:
            parts.append(f"{missing} not found")
        if pending:
            parts.append(f"reading details of {pending}…")
        self.summary.setText(" · ".join(parts) if total else "")

    def _sort_changed(self) -> None:
        self.refresh()
        self.sort_changed.emit(self.sort_order.value)

    def rescan(self, folder_ids: list[int] | None = None) -> None:
        if not self._service.db.folders():
            return
        self._scanned = 0
        self._set_scanning(True, "Scanning…")
        self._service.scan(folder_ids)

    def manage_folders(self) -> FoldersDialog:
        dialog = FoldersDialog(self._service, self)
        dialog.finished.connect(lambda _r: self.refresh())
        dialog.open()
        return dialog

    def add_folder(self, path: str) -> bool:
        try:
            folder = self._service.db.add_folder(path)
        except LibraryError as exc:
            self.status_changed.emit(str(exc))
            return False
        self._set_scanning(True, f"Scanning {folder.path}…")
        self._service.scan([folder.id])
        self.refresh()
        return True

    def remove_unavailable(self) -> None:
        removed = self._service.db.remove_unavailable()
        self.status_changed.emit(f"Removed {removed} unavailable entries (files were not touched)")
        self.refresh()

    def _set_scanning(self, scanning: bool, text: str = "") -> None:
        self.cancel_button.setVisible(scanning)
        self.scan_button.setVisible(not scanning)
        if text:
            self.status_changed.emit(text)

    def _on_library_event(self, event: object) -> None:
        if not isinstance(event, LibraryEvent):
            return
        if isinstance(event, ScanProgress):
            self._set_scanning(True)
            self.status_changed.emit(f"Scanning {event.folder} · {event.files} files")
        elif isinstance(event, ScanFinished):
            files = sum(s.files for s in event.summaries)
            missing = sum(s.missing for s in event.summaries)
            offline = [s.folder for s in event.summaries if not s.available]
            text = f"Scan finished · {files} files"
            if missing:
                text += f" · {missing} no longer found"
            if offline:
                text += f" · not reachable: {', '.join(offline)}"
            if any(s.cancelled for s in event.summaries):
                text = "Scan stopped · files found so far are kept"
            self.status_changed.emit(text)
            self.refresh()
            self.refresh_current_tab()
        elif isinstance(event, MetadataUpdated):
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        elif isinstance(event, WorkerIdle):
            self._set_scanning(False)
            self._refresh_timer.stop()
            self.refresh()
            self.refresh_current_tab()

    # -------------------------------------------------------- actions
    def selected_entries(self) -> list[MediaEntry]:
        rows = sorted(i.row() for i in self.view.selectionModel().selectedIndexes())
        return [self.model.entry(r) for r in rows]

    def _play_rows(self, rows: list[int]) -> None:
        entries = [self.model.entry(r) for r in rows]
        playable = [e for e in entries if e.available]
        if not playable:
            self.status_changed.emit("This file was not found. It may have been moved or deleted.")
            return
        if len(playable) == 1:
            self.play_requested.emit(playable[0].path)
        else:
            self.play_list_requested.emit([e.path for e in playable], 0)

    def _context_menu(self, pos: QPoint) -> None:
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        if not self.view.selectionModel().isSelected(index):
            self.view.setCurrentIndex(index)
        entries = self.selected_entries()
        menu = self.build_context_menu(entries)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def build_context_menu(self, entries: list[MediaEntry]) -> QMenu:
        menu = QMenu(self)
        rows = [self.model.entries.index(e) for e in entries]
        play = menu.addAction("Play" if len(entries) == 1 else f"Play {len(entries)} files")
        play.triggered.connect(lambda: self._play_rows(rows))
        self._fill_playlist_menu(menu.addMenu("Add to playlist"), entries)
        if len(entries) == 1 and entries[0].available:
            reveal = menu.addAction("Show in folder")
            reveal.triggered.connect(lambda: reveal_in_explorer(entries[0].path))
        menu.addSeparator()
        remove = menu.addAction("Remove from library")
        remove.setToolTip("The file stays on disk")
        remove.triggered.connect(lambda: self.remove_entries(entries))
        return menu

    def add_to_playlist(self, playlist_id: int, entries: list[MediaEntry]) -> None:
        self._service.db.add_to_playlist(playlist_id, [e.path for e in entries])
        self.playlists.refresh()
        self.status_changed.emit(f"Added {len(entries)} to the playlist")

    def _add_to_new_playlist(self, entries: list[MediaEntry]) -> None:
        pid = self.playlists.new_playlist()
        if pid is not None:
            self.add_to_playlist(pid, entries)

    def remove_entries(self, entries: list[MediaEntry]) -> None:
        self._service.db.remove_media([e.id for e in entries])
        self.status_changed.emit(
            f"Removed {len(entries)} from the library (files were not touched; a rescan adds them back)"
        )
        self.refresh()

    def thumbnail_for(self, path: str) -> Path | None:
        entry = self._service.db.media_by_path(path)
        return self._service.thumbnail_path(entry.thumbnail) if entry else None
