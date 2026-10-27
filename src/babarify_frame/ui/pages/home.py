"""Home page: the empty state. One obvious action (open a file) plus drop zone and key hints."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from babarify_frame import BRAND, PRODUCT_NAME, TAGLINE
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import glyph_icon

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


class HomePage(QWidget):
    open_requested = Signal()

    def __init__(self, logo: QIcon, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.XXL, theme.XXL, theme.XXL, theme.XL)
        outer.addStretch(1)

        column = QVBoxLayout()
        column.setSpacing(theme.M)
        column.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo_label = QLabel()
        logo_label.setPixmap(logo.pixmap(88, 88))
        logo_label.setAccessibleName(f"{PRODUCT_NAME} logo")
        column.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(_label(BRAND.upper(), "brand"), alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(_label(PRODUCT_NAME, "display"), alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(_label(TAGLINE, "tagline"), alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(theme.XL)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        self.drop_zone.setMinimumWidth(360)
        self.drop_zone.setMaximumWidth(560)
        zone = QVBoxLayout(self.drop_zone)
        zone.setContentsMargins(theme.XL, theme.XL, theme.XL, theme.XL)
        zone.setSpacing(theme.M)
        drop_icon = glyph_icon("drop", theme.CYAN, theme.TEXT_DISABLED, size=48)
        if drop_icon is not None:
            icon_label = QLabel()
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
        column.addWidget(self._shortcut_grid(), alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(column)
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

    def set_engine_ready(self, ready: bool) -> None:
        self.open_button.setEnabled(ready)

    def set_drag_active(self, active: bool) -> None:
        self.drop_zone.setProperty("dragActive", active)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)
