"""Small player widgets: video surface, seek slider, time formatting."""

from __future__ import annotations

from functools import cache

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider, QWidget

# Segoe Fluent Icons (Windows 11) / Segoe MDL2 Assets (Windows 10) code points.
GLYPHS = {
    "open": "",
    "play": "",
    "pause": "",
    "stop": "",
    "volume": "",
    "mute": "",
    "fullscreen": "",
    "exit_fullscreen": "",
}


@cache
def _icon_font_family() -> str | None:
    families = set(QFontDatabase.families())
    return next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)


def glyph_icon(name: str, color: str, disabled_color: str, size: int = 32) -> QIcon | None:
    """Render a Windows icon-font glyph as a QIcon, or None if no icon font is installed."""
    family = _icon_font_family()
    if family is None:
        return None
    icon = QIcon()
    for mode, tint in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, disabled_color)):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont(family)
        font.setPixelSize(int(size * 0.62))
        painter.setFont(font)
        painter.setPen(QColor(tint))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, GLYPHS[name])
        painter.end()
        icon.addPixmap(pixmap, mode)
    return icon


def format_time(ms: int | None) -> str:
    """``mm:ss`` below an hour, ``h:mm:ss`` above; ``--:--`` when unknown."""
    if ms is None or ms < 0:
        return "--:--"
    seconds = ms // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


class VideoSurface(QWidget):
    """Native child window the engine renders into. Emits ``double_clicked`` for fullscreen."""

    double_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background: black;")
        self.setAccessibleName("Video")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class SeekSlider(QSlider):
    """Horizontal slider that jumps to the clicked position and reports user seeks.

    ``seek_requested`` fires when the user releases the handle or clicks the groove;
    programmatic ``setValue`` calls never trigger it.
    """

    seek_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 0)
        self.setAccessibleName("Seek")
        self.sliderReleased.connect(lambda: self.seek_requested.emit(self.value()))

    @property
    def user_dragging(self) -> bool:
        return self.isSliderDown()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > 0:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
            )
            if not handle.contains(event.position().toPoint()):
                value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), int(event.position().x()), self.width()
                )
                self.setValue(value)
                self.seek_requested.emit(value)
                event.accept()
                return
        super().mousePressEvent(event)
