"""Small player widgets: video surface, seek slider, time formatting."""

from __future__ import annotations

from functools import cache

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import QLabel, QSlider, QStyle, QStyleOptionSlider, QWidget

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
    "back": "",  # Rewind
    "forward": "",  # FastForward
    "home": "",
    "now_playing": "",  # Video
    "settings": "",
    "info": "",
    "error": "",
    "music": "",
    "drop": "",  # Download / drop target
    "subtitles": "",  # ClosedCaption
    "shuffle": "\ue8b1",
    "repeat": "\ue8ee",
    "repeat_one": "\ue8ed",
    "previous": "\ue892",
    "next": "\ue893",
    "queue": "\ue8fd",
    "library": "",  # Library
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


def plain_text(*labels: QLabel) -> None:
    """Show text exactly as given. QLabel otherwise guesses, and renders text that looks like HTML
    as rich text (M10 security review): file tags, chapter titles, server error messages and
    stream addresses are untrusted and must never be interpreted."""
    for label in labels:
        label.setTextFormat(Qt.TextFormat.PlainText)


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
    programmatic ``setValue`` calls never trigger it. M8: chapter starts and bookmarks are
    drawn as marks, and ``hovered`` reports the time under the mouse (for previews).
    """

    seek_requested = Signal(int)
    hovered = Signal(int, QPoint)  # time under the mouse, global position of the groove point
    hover_left = Signal()

    CHAPTER_COLOR = "#8FA3BF"
    BOOKMARK_COLOR = "#F5B544"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 0)
        self.setAccessibleName("Seek")
        self.setMouseTracking(True)
        self.sliderReleased.connect(lambda: self.seek_requested.emit(self.value()))
        self._chapter_marks: tuple[int, ...] = ()
        self._bookmark_marks: tuple[int, ...] = ()

    @property
    def user_dragging(self) -> bool:
        return self.isSliderDown()

    def set_marks(self, chapters: tuple[int, ...], bookmarks: tuple[int, ...]) -> None:
        """Times (ms) of chapter starts (the first one, at 0, is not drawn) and bookmarks."""
        if (chapters, bookmarks) != (self._chapter_marks, self._bookmark_marks):
            self._chapter_marks, self._bookmark_marks = chapters, bookmarks
            self.update()

    @property
    def marks(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return self._chapter_marks, self._bookmark_marks

    def value_at(self, x: int) -> int:
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), x, self.width())

    def x_of(self, value: int) -> int:
        return QStyle.sliderPositionFromValue(self.minimum(), self.maximum(), value, self.width())

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self.maximum() <= 0 or not (self._chapter_marks or self._bookmark_marks):
            return
        painter = QPainter(self)
        mid = self.height() // 2
        for times, color, half in (
            (self._chapter_marks, self.CHAPTER_COLOR, 5),
            (self._bookmark_marks, self.BOOKMARK_COLOR, 7),
        ):
            painter.setPen(QColor(color))
            for ms in times:
                if 0 < ms <= self.maximum():
                    x = self.x_of(ms)
                    painter.drawLine(x, mid - half, x, mid + half)
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if self.maximum() > 0:
            x = max(0, min(self.width() - 1, int(event.position().x())))
            self.hovered.emit(self.value_at(x), self.mapToGlobal(QPoint(x, 0)))

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.hover_left.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > 0:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
            )
            if not handle.contains(event.position().toPoint()):
                value = self.value_at(int(event.position().x()))
                self.setValue(value)
                self.seek_requested.emit(value)
                event.accept()
                return
        super().mousePressEvent(event)
