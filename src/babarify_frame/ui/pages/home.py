"""Home page: one obvious action (open a file) plus drop zone and key hints.

M6: once there is playback history, the page also shows *Continue watching* (files stopped part
way, with progress) and *Recently played*. History is local; Settings → Privacy clears it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame import PRODUCT_NAME, TAGLINE
from babarify_frame.library.models import HistoryEntry
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import format_time, glyph_icon

CONTINUE_LIMIT = 8
RECENT_LIMIT = 8
CARD_THUMB = QSize(192, 108)

SHORTCUTS = (
    ("Ctrl+O", "Open a file"),
    ("Space", "Play / pause"),
    ("← →", "Seek back / forward"),
    ("↑ ↓", "Volume"),
    ("M", "Mute"),
    ("F", "Fullscreen"),
)


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    return label


class BrandTitle(QLabel):
    """The product name in the colours of the logo and the main button, in every colour theme."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("display")

    def paintEvent(self, event: QPaintEvent) -> None:
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor(theme.BLUE))
        gradient.setColorAt(1, QColor(theme.CYAN))
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QPen(gradient, 1))
        painter.drawText(self.rect(), int(self.alignment()), self.text())
        painter.end()


def ago(timestamp: float, now: float | None = None) -> str:
    seconds = max(0, int((now or time.time()) - timestamp))
    if seconds < 60:
        return "just now"
    for unit, size in (("day", 86_400), ("hour", 3_600), ("minute", 60)):
        if seconds >= size:
            count = seconds // size
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    return "just now"


def remaining_text(entry: HistoryEntry) -> str:
    if entry.duration_ms:
        return f"{format_time(max(0, entry.duration_ms - entry.position_ms))} left"
    return f"at {format_time(entry.position_ms)}"


def card_pixmap(thumbnail: Path | None, progress: float) -> QPixmap:
    """Thumbnail letterboxed on black with the watched fraction drawn along the bottom."""
    pixmap = QPixmap(CARD_THUMB)
    pixmap.fill(QColor("#000000"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    source = QPixmap(str(thumbnail)) if thumbnail is not None and thumbnail.is_file() else QPixmap()
    if not source.isNull():
        scaled = source.scaled(
            CARD_THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(
            (CARD_THUMB.width() - scaled.width()) // 2, (CARD_THUMB.height() - scaled.height()) // 2, scaled
        )
    else:
        icon = glyph_icon("now_playing", theme.TEXT_DISABLED, theme.TEXT_DISABLED, size=48)
        if icon is not None:
            icon.paint(painter, QRect(72, 30, 48, 48))
    bar_y = CARD_THUMB.height() - 4
    painter.fillRect(QRect(0, bar_y, CARD_THUMB.width(), 4), QColor(255, 255, 255, 60))
    painter.fillRect(QRect(0, bar_y, int(CARD_THUMB.width() * progress), 4), QColor(theme.CYAN))
    painter.end()
    return pixmap


class HomePage(QWidget):
    open_requested = Signal()
    play_requested = Signal(str)  # a path from history
    forget_requested = Signal(str)  # remove one path from history

    def __init__(self, logo: QIcon, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(theme.XXL, theme.XXL, theme.XXL, theme.XL)
        outer.addStretch(1)

        column = QVBoxLayout()
        column.setSpacing(theme.M)
        column.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo_label = QLabel()
        logo_label.setPixmap(logo.pixmap(88, 88))
        logo_label.setAccessibleName(f"{PRODUCT_NAME} logo")
        self._hero = [
            logo_label,
            BrandTitle(PRODUCT_NAME),
            _label(TAGLINE, "tagline"),
        ]
        for widget in self._hero:
            column.addWidget(widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(theme.XL)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setMinimumWidth(360)
        self.drop_zone.setMaximumWidth(560)
        zone = QVBoxLayout(self.drop_zone)
        zone.setContentsMargins(theme.XL, theme.XL, theme.XL, theme.XL)
        zone.setSpacing(theme.M)
        drop_icon = glyph_icon("drop", theme.CYAN, theme.TEXT_DISABLED, size=48)
        self._drop_icon: QLabel | None = None
        if drop_icon is not None:
            icon_label = QLabel()
            self._drop_icon = icon_label
            icon_label.setPixmap(drop_icon.pixmap(QSize(40, 40)))
            zone.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        zone.addWidget(
            _label("Drop a video or audio file here", "subtitle"), alignment=Qt.AlignmentFlag.AlignHCenter
        )
        self.open_button = QPushButton("Open file…")
        self.open_button.setObjectName("primary")
        self.open_button.setAccessibleName("Open file")
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.clicked.connect(self.open_requested)
        zone.addWidget(self.open_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        zone.addWidget(_label("or press Ctrl+O", "caption"), alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.drop_zone, alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(theme.L)
        self._shortcuts = self._shortcut_grid()
        column.addWidget(self._shortcuts, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(column)
        outer.addSpacing(theme.XL)
        self.history_panel = self._build_history()
        outer.addWidget(self.history_panel)
        outer.addStretch(2)
        outer.addWidget(
            _label("Local playback only · No account · No telemetry", "caption"),
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

    def _shortcut_grid(self) -> QWidget:
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setHorizontalSpacing(theme.XL)
        grid.setVerticalSpacing(theme.S)
        for i, (keys, action) in enumerate(SHORTCUTS):
            row, col = divmod(i, 3)
            cell = QHBoxLayout()
            cell.setSpacing(theme.S)
            key_cap = _label(keys, "kbd")
            key_cap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            cell.addWidget(key_cap)
            cell.addWidget(_label(action, "muted"))
            grid.addLayout(cell, row, col)
        return grid_widget

    # ------------------------------------------------------- history (M6)
    def _build_history(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(theme.M)
        self.continue_title = _label("Continue watching", "subtitle")
        box.addWidget(self.continue_title)
        self.continue_row = QWidget()
        self.continue_row.setObjectName("page")  # page background, not the default viewport colour
        self._continue_box = QHBoxLayout(self.continue_row)
        self._continue_box.setContentsMargins(0, 0, 0, 0)
        self._continue_box.setSpacing(theme.M)
        self._continue_box.addStretch(1)
        row_scroll = QScrollArea()
        row_scroll.setWidgetResizable(True)
        row_scroll.setFrameShape(QFrame.Shape.NoFrame)
        row_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row_scroll.setFixedHeight(CARD_THUMB.height() + 72)
        row_scroll.setWidget(self.continue_row)
        self._continue_scroll = row_scroll
        box.addWidget(row_scroll)
        self.recent_title = _label("Recently played", "subtitle")
        box.addWidget(self.recent_title)
        self.recent = QListWidget()
        self.recent.setAccessibleName("Recently played")
        self.recent.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recent.itemActivated.connect(self._play_item)
        self.recent.customContextMenuRequested.connect(self._recent_menu)
        box.addWidget(self.recent)
        self.continue_cards: list[QToolButton] = []
        panel.hide()
        return panel

    def refresh_theme(self) -> None:
        icon = glyph_icon("drop", theme.CYAN, theme.TEXT_DISABLED, size=48)
        if self._drop_icon is not None and icon is not None:
            self._drop_icon.setPixmap(icon.pixmap(QSize(40, 40)))

    def set_history(
        self,
        continue_watching: list[HistoryEntry],
        recent: list[HistoryEntry],
        thumbnail_for: Callable[[HistoryEntry], Path | None],
    ) -> None:
        for card in self.continue_cards:
            card.deleteLater()
        self.continue_cards = []
        for entry in continue_watching[:CONTINUE_LIMIT]:
            card = QToolButton()
            card.setObjectName("continueCard")
            card.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            card.setIcon(QIcon(card_pixmap(thumbnail_for(entry), entry.progress)))
            card.setIconSize(CARD_THUMB)
            metrics = card.fontMetrics()
            title = metrics.elidedText(entry.title, Qt.TextElideMode.ElideMiddle, CARD_THUMB.width())
            card.setText(f"{title}\n{remaining_text(entry)}")
            card.setToolTip(f"{entry.path}\nResume at {format_time(entry.position_ms)}")
            card.setAccessibleName(f"Continue {entry.title}, {remaining_text(entry)}")
            card.setFixedWidth(CARD_THUMB.width() + 16)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.clicked.connect(lambda _=False, p=entry.path: self.play_requested.emit(p))
            card.customContextMenuRequested.connect(
                lambda pos, c=card, p=entry.path: self._forget_menu(c.mapToGlobal(pos), p)
            )
            self._continue_box.insertWidget(self._continue_box.count() - 1, card)
            self.continue_cards.append(card)
        has_continue = bool(self.continue_cards)
        self.continue_title.setVisible(has_continue)
        self._continue_scroll.setVisible(has_continue)

        self.recent.clear()
        for entry in recent[:RECENT_LIMIT]:
            state = "" if entry.available else " · not found"
            item = QListWidgetItem(f"{entry.title}    {ago(entry.last_played_at)}{state}")
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            item.setToolTip(entry.path)
            if not entry.available:
                item.setForeground(QColor(theme.TEXT_DISABLED))
            self.recent.addItem(item)
        row_height = self.recent.sizeHintForRow(0) if self.recent.count() else 34
        self.recent.setFixedHeight(min(RECENT_LIMIT, max(1, self.recent.count())) * row_height + 16)
        has_history = bool(recent)
        self.recent_title.setVisible(has_history)
        self.recent.setVisible(has_history)
        self.history_panel.setVisible(has_history)
        # With history, the page is a dashboard: hide the large logo and key hints.
        for widget in (*self._hero, self._shortcuts):
            widget.setVisible(not has_history)

    def _play_item(self, item: QListWidgetItem) -> None:
        self.play_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _recent_menu(self, pos: QPoint) -> None:
        item = self.recent.itemAt(pos)
        if item is not None:
            self._forget_menu(
                self.recent.viewport().mapToGlobal(pos), str(item.data(Qt.ItemDataRole.UserRole))
            )

    def _forget_menu(self, global_pos: QPoint, path: str) -> None:
        menu = QMenu(self)
        play = menu.addAction("Play")
        play.triggered.connect(lambda: self.play_requested.emit(path))
        forget = menu.addAction("Remove from history")
        forget.triggered.connect(lambda: self.forget_requested.emit(path))
        menu.exec(global_pos)

    def set_engine_ready(self, ready: bool) -> None:
        self.open_button.setEnabled(ready)

    def set_drag_active(self, active: bool) -> None:
        self.drop_zone.setProperty("dragActive", active)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)
