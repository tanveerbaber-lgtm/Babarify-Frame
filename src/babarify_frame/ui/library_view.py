"""Library grid (M6): list model over ``MediaEntry`` rows and a card delegate.

The model holds plain records from one database query; thumbnails load lazily from disk the
first time a card is painted and are cached, so a library of thousands of files opens quickly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from babarify_frame.library.models import MediaEntry
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import format_time, glyph_icon

CARD = QSize(216, 176)
THUMB = QSize(200, 112)
ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1
_Index = QModelIndex | QPersistentModelIndex


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def describe(entry: MediaEntry) -> str:
    parts = []
    if entry.duration_ms:
        parts.append(format_time(entry.duration_ms))
    if entry.width and entry.height:
        parts.append(f"{entry.width}×{entry.height}")  # noqa: RUF001
    elif entry.probed and not entry.video_codec and entry.audio_codec:
        parts.append("Audio")
    parts.append(human_size(entry.size))
    return " · ".join(parts)


def tooltip(entry: MediaEntry, duplicates: list[str]) -> str:
    lines = [entry.name, entry.path, describe(entry)]
    codecs = " / ".join(c for c in (entry.video_codec, entry.audio_codec) if c)
    if codecs:
        lines.append(codecs)
    if not entry.available:
        lines.append("Not found: the file was moved, deleted or its drive is not connected.")
    elif entry.probed and not (entry.video_codec or entry.audio_codec or entry.duration_ms):
        lines.append("Details could not be read from this file.")
    if duplicates:
        lines.append("Same content as: " + "; ".join(duplicates[:3]) + (" …" if len(duplicates) > 3 else ""))
    return "\n".join(lines)


class LibraryModel(QAbstractListModel):
    def __init__(
        self,
        thumbnail_path: Callable[[str | None], Path | None],
        duplicates_of: Callable[[int], list[str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entries: list[MediaEntry] = []
        self._thumbnail_path = thumbnail_path
        self._duplicates_of = duplicates_of
        self._pixmaps: dict[str, QPixmap] = {}

    def set_entries(self, entries: list[MediaEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry(self, row: int) -> MediaEntry:
        return self._entries[row]

    @property
    def entries(self) -> list[MediaEntry]:
        return list(self._entries)

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.name
        if role == Qt.ItemDataRole.AccessibleTextRole:
            state = "" if entry.available else ", not found"
            return f"{entry.name}, {describe(entry)}{state}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return tooltip(entry, self._duplicates_of(entry.id) if entry.duplicates else [])
        if role == ENTRY_ROLE:
            return entry
        if role == Qt.ItemDataRole.DecorationRole:
            return self.thumbnail(entry)
        return None

    def thumbnail(self, entry: MediaEntry) -> QPixmap | None:
        if not entry.thumbnail:
            return None
        cached = self._pixmaps.get(entry.thumbnail)
        if cached is None:
            path = self._thumbnail_path(entry.thumbnail)
            cached = QPixmap(str(path)) if path is not None and path.is_file() else QPixmap()
            self._pixmaps[entry.thumbnail] = cached
        return cached if not cached.isNull() else None


class LibraryDelegate(QStyledItemDelegate):
    """Card: thumbnail (or a glyph), title, details line, progress and status badges."""

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        return CARD

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        entry = index.data(ENTRY_ROLE)
        if not isinstance(entry, MediaEntry):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 4, -4, -4)
        state = option.state
        selected = bool(state & QStyle.StateFlag.State_Selected)
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        painter.setPen(QColor(theme.CYAN) if selected else Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.SURFACE_RAISED if (selected or hovered) else theme.SURFACE))
        painter.drawRoundedRect(rect, 10, 10)

        thumb_rect = QRect(rect.x() + 4, rect.y() + 4, THUMB.width(), THUMB.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#000000"))
        painter.drawRoundedRect(thumb_rect, 6, 6)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            scaled = pixmap.scaled(
                thumb_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = thumb_rect.x() + (thumb_rect.width() - scaled.width()) // 2
            y = thumb_rect.y() + (thumb_rect.height() - scaled.height()) // 2
            if not entry.available:
                painter.setOpacity(0.35)
            painter.drawPixmap(x, y, scaled)
            painter.setOpacity(1.0)
        else:
            glyph = (
                "music" if (entry.probed and not entry.video_codec and entry.audio_codec) else "now_playing"
            )
            icon = glyph_icon(glyph, theme.TEXT_DISABLED, theme.TEXT_DISABLED, size=48)
            if icon is not None:
                icon.paint(painter, thumb_rect.adjusted(70, 26, -70, -26))

        if entry.position_ms and entry.duration_ms:
            fraction = max(0.0, min(1.0, entry.position_ms / entry.duration_ms))
            bar = QRect(thumb_rect.x(), thumb_rect.bottom() - 3, thumb_rect.width(), 4)
            painter.setBrush(QColor(255, 255, 255, 60))
            painter.drawRect(bar)
            painter.setBrush(QColor(theme.CYAN))
            painter.drawRect(QRect(bar.x(), bar.y(), int(bar.width() * fraction), bar.height()))

        badge = "Not found" if not entry.available else ("Duplicate" if entry.duplicates else "")
        if badge:
            font = QFont(painter.font())
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
            painter.setFont(font)
            width = painter.fontMetrics().horizontalAdvance(badge) + 12
            badge_rect = QRect(thumb_rect.right() - width - 6, thumb_rect.y() + 6, width, 18)
            painter.setBrush(QColor(theme.AMBER if entry.available else theme.RED))
            painter.drawRoundedRect(badge_rect, 9, 9)
            painter.setPen(QColor(theme.ON_ACCENT))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge)
            painter.setFont(option.font)

        text_rect = QRect(rect.x() + 8, thumb_rect.bottom() + 8, rect.width() - 16, 20)
        painter.setPen(QColor(theme.TEXT if entry.available else theme.TEXT_DISABLED))
        metrics = painter.fontMetrics()
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(entry.name, Qt.TextElideMode.ElideMiddle, text_rect.width()),
        )
        detail_rect = text_rect.translated(0, 20)
        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(
            detail_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(describe(entry), Qt.TextElideMode.ElideRight, detail_rect.width()),
        )
        painter.restore()
