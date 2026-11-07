"""The library's For you tab: a recap of what's been played, and what to play next."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.library import recap
from babarify_frame.library.music import GroupKind, group_songs
from babarify_frame.library.service import LibraryService
from babarify_frame.ui import theme


class ForYouPanel(QWidget):
    play_requested = Signal(list, int)  # paths, start

    def __init__(self, service: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self._box = QVBoxLayout(content)
        self._box.setSpacing(theme.S)
        self.summary = QLabel()
        self.summary.setObjectName("subtitle")
        self.summary.setWordWrap(True)
        self._box.addWidget(self.summary)
        self.most_played = self._section("Most played")
        self.artists = self._section("Top artists")
        self.albums = self._section("Top albums")
        self.never_played = self._section("Never played")
        self._box.addStretch(1)

    def _section(self, title: str) -> QListWidget:
        heading = QLabel(title)
        heading.setObjectName("title")
        self._box.addWidget(heading)
        items = QListWidget()
        items.setAccessibleName(title)
        items.setFrameShape(QFrame.Shape.NoFrame)
        items.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        items.itemActivated.connect(self._play)
        self._box.addWidget(items)
        return items

    def refresh(self) -> None:
        db = self._service.db
        songs = db.songs()
        found = recap.build(songs, db.play_counts())
        if found.plays:
            self.summary.setText(
                f"You've played {recap.counted(found.songs_played, 'song')} "
                f"{recap.counted(found.plays, 'time')}: about "
                f"{recap.listening_time(found.listened_ms)} of listening."
            )
        else:
            self.summary.setText("Play some songs, and your recap appears here.")
        artists = {g.title: g for g in group_songs(songs, GroupKind.ARTIST)}
        albums = {g.title: g for g in group_songs(songs, GroupKind.ALBUM)}
        self._fill(
            self.most_played,
            [(f"{s.display_title}  ·  {recap.counted(n, 'play')}", [s.path]) for s, n in found.top_songs],
        )
        self._fill(
            self.artists,
            [(f"{name}  ·  {recap.counted(n, 'play')}", [s.path for s in artists[name].songs])
             for name, n in found.top_artists
             if name in artists],
        )  # fmt: skip
        self._fill(
            self.albums,
            [(f"{name}  ·  {recap.counted(n, 'play')}", [s.path for s in albums[name].songs])
             for name, n in found.top_albums
             if name in albums],
        )  # fmt: skip
        self._fill(self.never_played, [(s.display_title, [s.path]) for s in found.never_played])

    @staticmethod
    def _fill(items: QListWidget, rows: list[tuple[str, list[str]]]) -> None:
        items.clear()
        for text, paths in rows:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, paths)
            items.addItem(item)
        height = items.sizeHintForRow(0) * items.count() + 4 if items.count() else 0
        items.setFixedHeight(height)
        items.setVisible(items.count() > 0)

    def _play(self, item: QListWidgetItem) -> None:
        self.play_requested.emit(list(item.data(Qt.ItemDataRole.UserRole)), 0)
