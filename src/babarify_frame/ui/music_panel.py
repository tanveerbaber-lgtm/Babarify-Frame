"""The Library's Songs, Albums and Artists tabs. Everything shown comes from the files' own tags."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QAbstractListModel,
    QFile,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.library.models import MediaEntry
from babarify_frame.library.music import SONG_SORT_LABELS, GroupKind, SongGroup, SongSort, group_songs
from babarify_frame.library.service import LibraryService
from babarify_frame.ui import theme
from babarify_frame.ui.library_view import CARD, THUMB, LibraryModel
from babarify_frame.ui.widgets import format_time, glyph_icon, plain_text

ROW = 64
SEARCH_DELAY_MS = 200
ART = 48
_Index = QModelIndex | QPersistentModelIndex
GROUP_ROLE = Qt.ItemDataRole.UserRole + 2
ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1
_ALBUM_CARD = QSize(CARD.width(), THUMB.width() + 60)


def song_count(count: int) -> str:
    return "1 song" if count == 1 else f"{count} songs"


def _draw_picture(painter: QPainter, rect: QRect, pixmap: QPixmap | None, glyph: str, radius: int) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.SURFACE_RAISED))
    painter.drawRoundedRect(rect, radius, radius)
    if pixmap is not None and not pixmap.isNull():
        scaled = pixmap.scaled(
            rect.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        source = QRect(
            (scaled.width() - rect.width()) // 2,
            (scaled.height() - rect.height()) // 2,
            rect.width(),
            rect.height(),
        )
        painter.save()
        painter.setBrush(scaled)
        painter.setBrushOrigin(rect.x() - source.x(), rect.y() - source.y())
        painter.drawRoundedRect(rect, radius, radius)
        painter.restore()
        return
    icon = glyph_icon(glyph, theme.TEXT_DISABLED, theme.TEXT_DISABLED, size=48)
    if icon is not None:
        inset = rect.width() // 4
        icon.paint(painter, rect.adjusted(inset, inset, -inset, -inset))


class SongDelegate(QStyledItemDelegate):
    """One song on a row: picture, title, artist and album, length."""

    def __init__(self, model: LibraryModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        return QSize(option.rect.width(), ROW)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        entry = index.data(ENTRY_ROLE)
        if not isinstance(entry, MediaEntry):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.SURFACE_RAISED))
            painter.drawRoundedRect(rect, 8, 8)
        art = QRect(rect.x() + 6, rect.y() + (rect.height() - ART) // 2, ART, ART)
        _draw_picture(painter, art, self._model.thumbnail(entry), "music", 8)
        metrics = painter.fontMetrics()
        right = rect.right() - 10
        length = format_time(entry.duration_ms) if entry.duration_ms else ""
        length_width = metrics.horizontalAdvance(length) + 4
        left = art.right() + 12
        title_rect = QRect(left, rect.y() + 10, right - left - length_width - 12, 20)
        painter.setPen(QColor(theme.TEXT if entry.available else theme.TEXT_DISABLED))
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(entry.display_title, Qt.TextElideMode.ElideRight, title_rect.width()),
        )
        painter.setPen(QColor(theme.TEXT_MUTED))
        detail = entry.artist or "Unknown artist"
        if entry.album:
            detail += f"  ·  {entry.album}"
        if not entry.available:
            detail = f"Not found  ·  {detail}"
        detail_rect = title_rect.translated(0, 22)
        painter.drawText(
            detail_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(detail, Qt.TextElideMode.ElideRight, detail_rect.width()),
        )
        painter.drawText(
            QRect(right - length_width, rect.y(), length_width, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            length,
        )
        painter.restore()


class GroupModel(QAbstractListModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.groups: list[SongGroup] = []

    def set_groups(self, groups: list[SongGroup]) -> None:
        self.beginResetModel()
        self.groups = groups
        self.endResetModel()

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.groups)

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        group = self.groups[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return group.title
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{group.title}, {song_count(len(group.songs))}"
        if role == GROUP_ROLE:
            return group
        return None


class GroupDelegate(QStyledItemDelegate):
    """An album as a card with its picture, or an artist on a row with a round one."""

    def __init__(self, songs: LibraryModel, kind: GroupKind, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._songs = songs
        self._kind = kind

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        return _ALBUM_CARD if self._kind is GroupKind.ALBUM else QSize(option.rect.width(), ROW)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        group = index.data(GROUP_ROLE)
        if not isinstance(group, SongGroup):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.SURFACE_RAISED))
            painter.drawRoundedRect(rect, 10, 10)
        first = group.picture
        pixmap = self._songs.thumbnail(first) if first is not None else None
        metrics = painter.fontMetrics()
        if self._kind is GroupKind.ALBUM:
            side = rect.width() - 8
            art = QRect(rect.x() + 4, rect.y() + 4, side, side)
            _draw_picture(painter, art, pixmap, "music", 10)
            text = QRect(rect.x() + 8, art.bottom() + 6, rect.width() - 16, 20)
            detail = group.artist
        else:
            art = QRect(rect.x() + 6, rect.y() + (rect.height() - ART) // 2, ART, ART)
            _draw_picture(painter, art, pixmap, "music", ART // 2)
            text = QRect(art.right() + 12, rect.y() + 6, rect.width() - ART - 24, 20)
            detail = song_count(len(group.songs))
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(
            text,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(group.title, Qt.TextElideMode.ElideRight, text.width()),
        )
        painter.setPen(QColor(theme.TEXT_MUTED))
        below = text.translated(0, 20)
        painter.drawText(
            below,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(detail, Qt.TextElideMode.ElideRight, below.width()),
        )
        painter.restore()


def move_to_recycle_bin(path: str) -> bool:
    # Some versions of PySide6 return (moved, new path), and a tuple always counts as true.
    result = QFile.moveToTrash(path)
    return bool(result[0] if isinstance(result, tuple) else result)


def delete_from_disk(parent: QWidget, service: LibraryService, entries: list[MediaEntry]) -> str | None:
    """After asking, move files to the Recycle Bin and take them out of the library. Says what happened."""
    count = len(entries)
    question = (
        f"Move {entries[0].name} to the Recycle Bin?"
        if count == 1
        else f"Move {count} files to the Recycle Bin?"
    )
    if QMessageBox.question(parent, "Delete from disk", question) != QMessageBox.StandardButton.Yes:
        return None
    deleted = [entry for entry in entries if move_to_recycle_bin(entry.path)]
    service.db.remove_media([entry.id for entry in deleted])
    if len(deleted) == count:
        return f"Moved {count} to the Recycle Bin"
    left = count - len(deleted)
    moved = f"Moved {len(deleted)} to the Recycle Bin."
    return f"{moved} {left} could not be moved; a file can't move while it plays."


class EditDetailsDialog(QDialog):
    """Correct a song in the library. The file itself isn't changed."""

    def __init__(self, service: LibraryService, entry: MediaEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit details")
        self.setMinimumWidth(420)
        self._service = service
        self._entry = entry
        form = QFormLayout(self)
        note = QLabel("Saved in this app. The file itself isn't changed, so other apps still see its tags.")
        note.setWordWrap(True)
        form.addRow(note)
        self.title_box = QLineEdit(entry.title or "")
        self.artist_box = QLineEdit(entry.artist or "")
        self.album_box = QLineEdit(entry.album or "")
        form.addRow("Title", self.title_box)
        form.addRow("Artist", self.artist_box)
        form.addRow("Album", self.album_box)
        self.cover_button = QPushButton("Change cover…")
        self.cover_button.clicked.connect(self.choose_cover)
        form.addRow("", self.cover_button)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a cover", "", "Pictures (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path and not self._service.set_cover_from_file(self._entry.path, path):
            QMessageBox.warning(self, "Cover", "That picture couldn't be used.")

    def save(self) -> None:
        self._service.db.edit_tags(
            self._entry.path, self.title_box.text(), self.artist_box.text(), self.album_box.text()
        )
        self.accept()


class MusicPanel(QWidget):
    """Songs, or albums or artists that open to show their songs."""

    play_requested = Signal(list, int)  # paths, start
    shuffle_requested = Signal(list)  # paths
    play_next_requested = Signal(list)  # paths
    add_to_queue_requested = Signal(list)  # paths
    status_changed = Signal(str)

    def __init__(
        self,
        service: LibraryService,
        kind: GroupKind | None,
        add_to_playlist_menu: Callable[[QMenu, list[MediaEntry]], None],
        reveal: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self.kind = kind
        self._add_to_playlist_menu = add_to_playlist_menu
        self._reveal = reveal
        self._open_group: SongGroup | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(theme.M)

        tools = QHBoxLayout()
        self.back_button = QPushButton("← Back")
        self.back_button.setAccessibleName("Back")
        self.back_button.hide()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles, artists and albums")
        self.search.setAccessibleName("Search music")
        self.search.setClearButtonEnabled(True)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Sort songs")
        for order, text in SONG_SORT_LABELS.items():
            self.sort.addItem(text, order.value)
        self.sort.setVisible(kind is None)
        self.shuffle_button = QPushButton("Shuffle")
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("primary")
        tools.addWidget(self.back_button)
        tools.addWidget(self.search, stretch=1)
        tools.addWidget(self.sort)
        tools.addWidget(self.shuffle_button)
        tools.addWidget(self.play_button)
        box.addLayout(tools)
        self.summary = QLabel()
        self.summary.setObjectName("caption")
        plain_text(self.summary)
        box.addWidget(self.summary)

        self.songs = LibraryModel(service.thumbnail_path, service.db.duplicates_of, self)
        self.songs_view = QListView()
        self.songs_view.setAccessibleName("Songs")
        self.songs_view.setModel(self.songs)
        self.songs_view.setItemDelegate(SongDelegate(self.songs, self.songs_view))
        self.songs_view.setUniformItemSizes(True)
        self.songs_view.setMouseTracking(True)
        self.songs_view.setFrameShape(QListView.Shape.NoFrame)
        self.songs_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.songs_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.groups = GroupModel(self)
        self.groups_view = QListView()
        self.groups_view.setModel(self.groups)
        self.groups_view.setMouseTracking(True)
        self.groups_view.setFrameShape(QListView.Shape.NoFrame)
        if kind is not None:
            self.groups_view.setAccessibleName("Albums" if kind is GroupKind.ALBUM else "Artists")
            self.groups_view.setItemDelegate(GroupDelegate(self.songs, kind, self.groups_view))
            self.groups_view.setUniformItemSizes(True)
            if kind is GroupKind.ALBUM:
                self.groups_view.setViewMode(QListView.ViewMode.IconMode)
                self.groups_view.setResizeMode(QListView.ResizeMode.Adjust)
                self.groups_view.setMovement(QListView.Movement.Static)
                self.groups_view.setGridSize(_ALBUM_CARD + QSize(theme.S, theme.S))
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.stack = QStackedWidget()
        for widget in (self.empty, self.songs_view, self.groups_view):
            self.stack.addWidget(widget)
        box.addWidget(self.stack, stretch=1)

        # Waits for a pause in typing: a very large library takes a moment to search.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self.sort.currentIndexChanged.connect(lambda _i: self.refresh())
        self.back_button.clicked.connect(self.close_group)
        self.play_button.clicked.connect(self.play_all)
        self.shuffle_button.clicked.connect(self.shuffle_all)
        self.songs_view.activated.connect(lambda index: self.play_from(index.row()))
        self.songs_view.customContextMenuRequested.connect(self._context_menu)
        self.groups_view.activated.connect(lambda index: self.open_group(self.groups.groups[index.row()]))

    # ---------------------------------------------------------- data
    def refresh(self) -> None:
        order = SongSort(self.sort.currentData())
        found = self._service.db.songs(self.search.text().strip(), order)
        if self.kind is None:
            self._show_songs(found)
            self.summary.setText(song_count(len(found)))
            return
        groups = group_songs(found, self.kind)
        self.groups.set_groups(groups)
        if self._open_group is not None:
            same = next((g for g in groups if g.key == self._open_group.key), None)
            if same is not None:
                self.open_group(same)
                return
            self.close_group()
            return
        noun = "album" if self.kind is GroupKind.ALBUM else "artist"
        self.summary.setText(f"{len(groups)} {noun}{'' if len(groups) == 1 else 's'}")
        self.stack.setCurrentWidget(self.groups_view if groups else self.empty)
        self._set_empty_text()
        self._enable_buttons(bool(found))

    def _show_songs(self, songs: list[MediaEntry]) -> None:
        self.songs.set_entries(songs)
        self.stack.setCurrentWidget(self.songs_view if songs else self.empty)
        self._set_empty_text()
        self._enable_buttons(bool(songs))

    def _set_empty_text(self) -> None:
        if self.search.text().strip():
            self.empty.setText("Nothing matches your search.")
        elif self._service.db.folders():
            self.empty.setText(
                "No music found yet. Add a folder that holds songs, or wait for the scan to finish."
            )
        else:
            self.empty.setText(
                "Choose the folders that hold your music, using Folders… at the top of this page."
            )

    def _enable_buttons(self, enabled: bool) -> None:
        self.play_button.setEnabled(enabled)
        self.shuffle_button.setEnabled(enabled)

    # -------------------------------------------------------- groups
    def open_group(self, group: SongGroup) -> None:
        self._open_group = group
        self._show_songs(list(group.songs))
        self.back_button.show()
        detail = f"{group.artist}  ·  " if group.artist else ""
        self.summary.setText(f"{group.title}  ·  {detail}{song_count(len(group.songs))}")

    def close_group(self) -> None:
        self._open_group = None
        self.back_button.hide()
        self.refresh()

    # ------------------------------------------------------- playing
    def _shown_songs(self) -> list[MediaEntry]:
        if self.kind is None or self._open_group is not None:
            return [song for song in self.songs.entries if song.available]
        return [song for group in self.groups.groups for song in group.songs if song.available]

    def play_all(self) -> None:
        songs = self._shown_songs()
        if songs:
            self.play_requested.emit([song.path for song in songs], 0)

    def shuffle_all(self) -> None:
        songs = self._shown_songs()
        if songs:
            self.shuffle_requested.emit([song.path for song in songs])

    def play_from(self, row: int) -> None:
        entries = self.songs.entries
        chosen = entries[row]
        if not chosen.available:
            self.status_changed.emit("This file was not found. It may have been moved or deleted.")
            return
        playable = [song for song in entries if song.available]
        self.play_requested.emit([song.path for song in playable], playable.index(chosen))

    # ---------------------------------------------------------- menu
    def _selected(self) -> list[MediaEntry]:
        rows = sorted(i.row() for i in self.songs_view.selectionModel().selectedIndexes())
        return [self.songs.entry(row) for row in rows]

    def _context_menu(self, pos: QPoint) -> None:
        index = self.songs_view.indexAt(pos)
        if not index.isValid():
            return
        if not self.songs_view.selectionModel().isSelected(index):
            self.songs_view.setCurrentIndex(index)
        self.build_context_menu(self._selected()).exec(self.songs_view.viewport().mapToGlobal(pos))

    def build_context_menu(self, entries: list[MediaEntry]) -> QMenu:
        menu = QMenu(self)
        paths = [entry.path for entry in entries if entry.available]
        play_next = menu.addAction("Play next")
        play_next.triggered.connect(lambda: self.play_next_requested.emit(paths))
        add_to_queue = menu.addAction("Add to queue")
        add_to_queue.triggered.connect(lambda: self.add_to_queue_requested.emit(paths))
        play_next.setEnabled(bool(paths))
        add_to_queue.setEnabled(bool(paths))
        db = self._service.db
        adding = not all(db.is_favourite(entry.path) for entry in entries)
        favourite = menu.addAction("Add to favourites" if adding else "Remove from favourites")
        favourite.triggered.connect(lambda: self.set_favourites(entries, adding))
        self._add_to_playlist_menu(menu.addMenu("Add to playlist"), entries)
        if len(entries) == 1 and entries[0].available:
            reveal = menu.addAction("Show in folder")
            reveal.triggered.connect(lambda: self._reveal(entries[0].path))
        if len(entries) == 1:
            edit = menu.addAction("Edit details…")
            edit.triggered.connect(lambda: self.edit_details(entries[0]))
        hide = menu.addAction("Hide")
        hide.setToolTip("The file stays on disk. Settings can bring it back.")
        hide.triggered.connect(lambda: self.hide_entries(entries))
        delete = menu.addAction("Delete from disk…")
        delete.setToolTip("Moves the file to the Recycle Bin")
        delete.triggered.connect(lambda: self.delete_entries(entries))
        return menu

    def edit_details(self, entry: MediaEntry) -> None:
        dialog = EditDetailsDialog(self._service, entry, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def delete_entries(self, entries: list[MediaEntry]) -> None:
        message = delete_from_disk(self, self._service, entries)
        if message is not None:
            self.status_changed.emit(message)
            self.refresh()

    def hide_entries(self, entries: list[MediaEntry]) -> None:
        self._service.db.hide_media([entry.path for entry in entries])
        self.status_changed.emit(f"Hid {len(entries)} from the library. Settings can bring them back.")
        self.refresh()

    def set_favourites(self, entries: list[MediaEntry], favourite: bool) -> None:
        for entry in entries:
            self._service.db.set_favourite(entry.path, entry.display_title, favourite)
        self.status_changed.emit("Added to favourites" if favourite else "Removed from favourites")
