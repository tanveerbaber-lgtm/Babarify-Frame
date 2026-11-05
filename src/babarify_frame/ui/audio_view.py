"""What the player shows for audio: the file's own picture or else an animation, with title and artist."""

from __future__ import annotations

import ctypes
import math
import sys
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.core import music
from babarify_frame.core.music import VisualStyle
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import plain_text

FRAME_MS = 33  # Thirty frames a second is smooth enough, and easy on the battery.
COLOURS = ("#5B62FF", "#9D4BF2", "#F12BD9", "#FF5F9E", "#FFA23E")
_EASE = 0.3
_SETTLED = 0.005
_FADE_STEP = 0.08
_MAX_BARS = 96
_SLOWEST_FRAME_MS = 100
_STILL_LEVEL = 0.4


def colour_across(fraction: float) -> QColor:
    """The animations' colours, side to side. A plain colour draws much faster than a gradient."""
    position = max(0.0, min(1.0, fraction)) * (len(COLOURS) - 1)
    index = min(int(position), len(COLOURS) - 2)
    start, end = QColor(COLOURS[index]), QColor(COLOURS[index + 1])
    part = position - index
    return QColor(
        round(start.red() + (end.red() - start.red()) * part),
        round(start.green() + (end.green() - start.green()) * part),
        round(start.blue() + (end.blue() - start.blue()) * part),
    )


def animations_allowed() -> bool:
    """False if Windows is set to show no animations; then the bars stand still."""
    if sys.platform != "win32":
        return True
    enabled = ctypes.c_int(1)
    get_client_area_animation = 0x1042
    ok = ctypes.windll.user32.SystemParametersInfoW(get_client_area_animation, 0, ctypes.byref(enabled), 0)
    return not ok or bool(enabled.value)


def colour_from(image: QImage) -> QColor:
    """A dark colour from the picture, to fill the screen around it. Dark enough for light text."""
    pixel = image.scaled(
        1, 1, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    colour = pixel.pixelColor(0, 0)
    return QColor.fromHsvF(
        max(0.0, colour.hueF()),
        min(0.8, colour.saturationF() * 1.3),
        max(0.1, min(0.3, colour.valueF() * 0.5)),
    )


class Visualizer(QWidget):
    """Five animations for audio with no picture. Decoration only: see ``music.level``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(120, 80)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._levels = [music.REST_LEVEL] * _MAX_BARS
        self._peaks = [music.REST_LEVEL] * _MAX_BARS
        self._started = time.monotonic()
        self._energy = 0.0
        self._fade = 1.0
        self._playing = False
        self.style_choice = VisualStyle.AUTO
        self.shown_style = VisualStyle.MIRROR
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._advance)

    @property
    def animating(self) -> bool:
        return self._playing and self.isVisible() and animations_allowed()

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self._keep_running()

    def set_style_choice(self, style: VisualStyle) -> None:
        self.style_choice = style
        self._keep_running()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._keep_running()

    def hideEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().hideEvent(event)
        self._timer.stop()

    def _keep_running(self) -> None:
        if self.isVisible() and not self._timer.isActive():
            self._timer.start()

    def _bar_count(self) -> int:
        width = max(1, self.width())
        if self.shown_style is VisualStyle.CIRCLE:
            return 48
        if self.shown_style is VisualStyle.CAPSULES:
            return max(15, min(_MAX_BARS, width // 44))
        if self.shown_style is VisualStyle.LIGHTS:
            return max(13, min(36, width // 40))
        return max(19, min(_MAX_BARS, width // 34))

    def _advance(self) -> None:
        moving = self.animating
        now_ms = int((time.monotonic() - self._started) * 1000)
        changing = self._move_towards_chosen_style(now_ms)
        count = self._bar_count()
        rest = _STILL_LEVEL if self._playing and not moving else music.REST_LEVEL
        settling = changing
        for bar in range(count):
            shape = 1.0 if self.shown_style is VisualStyle.CIRCLE else music.envelope(bar, count)
            target = music.level(bar, now_ms) * shape if moving else rest
            self._levels[bar] += (target - self._levels[bar]) * _EASE
            self._peaks[bar] = music.peak(self._peaks[bar], self._levels[bar])
            if abs(target - self._levels[bar]) > _SETTLED or self._peaks[bar] - self._levels[bar] > _SETTLED:
                settling = True
        wanted = 1.0 if moving else 0.12
        self._energy += (wanted - self._energy) * _EASE
        if abs(wanted - self._energy) > _SETTLED:
            settling = True
        self.update()
        if not moving and not settling:
            self._timer.stop()  # Nothing is moving: use no power until something changes.

    def _move_towards_chosen_style(self, now_ms: int) -> bool:
        chosen = music.auto_style(now_ms) if self.style_choice is VisualStyle.AUTO else self.style_choice
        if chosen != self.shown_style:
            self._fade -= _FADE_STEP
            if self._fade <= 0:
                self._fade = 0.0
                self.shown_style = chosen
            return True
        if self._fade < 1:
            self._fade = min(1.0, self._fade + _FADE_STEP)
            return True
        return False

    # ------------------------------------------------------------ drawing
    def _brush(self) -> QBrush:
        gradient = QLinearGradient(0, 0, self.width(), 0)
        for index, colour in enumerate(COLOURS):
            gradient.setColorAt(index / (len(COLOURS) - 1), QColor(colour))
        return QBrush(gradient)

    def paintEvent(self, event: QPaintEvent) -> None:
        started = time.perf_counter()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._brush())
        painter.setOpacity(self._fade)
        count = self._bar_count()
        draw = {
            VisualStyle.CAPSULES: self._draw_capsules,
            VisualStyle.WAVES: self._draw_waves,
            VisualStyle.CIRCLE: self._draw_circle,
            VisualStyle.LIGHTS: self._draw_lights,
        }.get(self.shown_style, self._draw_mirror)
        draw(painter, count)
        painter.end()
        # Never let drawing take more than about half of the main thread, however big or slow the screen.
        cost_ms = (time.perf_counter() - started) * 1000
        self._timer.setInterval(max(FRAME_MS, min(_SLOWEST_FRAME_MS, int(cost_ms * 2))))

    def _draw_mirror(self, painter: QPainter, count: int) -> None:
        """Solid bars with floating caps above a line, and their dimmer reflection below it."""
        width, height = self.width(), self.height()
        line = 3.0
        base = height * 0.56
        up = base - line
        down = height - base - line
        margin = width * 0.06
        slot = (width - 2 * margin) / count
        bar = slot * 0.74
        below = down / max(1.0, up)
        bright: list[QRectF] = [QRectF(margin / 2, base, width - margin, line)]
        dim: list[QRectF] = []
        for index in range(count):
            left = margin + index * slot + (slot - bar) / 2
            tall = self._levels[index] * up * 0.86
            top = self._peaks[index] * up * 0.86 + 12
            cap = max(2.0, self._peaks[index] * 9)
            bright.append(QRectF(left, base - tall, bar, tall))
            bright.append(QRectF(left, base - top - cap, bar, cap))
            dim.append(QRectF(left, base + line, bar, tall * below))
            dim.append(QRectF(left, base + line + top * below, bar, cap * below))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setOpacity(self._fade * 0.34)
        painter.drawRects(dim)
        painter.setOpacity(self._fade)
        painter.drawRects(bright)

    def _draw_capsules(self, painter: QPainter, count: int) -> None:
        """Rounded bars that grow from the middle in both directions."""
        slot = self.width() / count
        bar = slot * 0.58
        middle = self.height() / 2
        for index in range(count):
            half = max(bar / 2, self._levels[index] * middle * 0.94)
            painter.setBrush(colour_across(index / max(1, count - 1)))
            painter.drawRoundedRect(
                QRectF(index * slot + (slot - bar) / 2, middle - half, bar, half * 2), bar / 2, bar / 2
            )

    def _draw_waves(self, painter: QPainter, _count: int) -> None:
        """Layers of smooth waves, each with a bright edge and a soft body."""
        t = time.monotonic() - self._started
        width, middle = self.width(), self.height() / 2
        steps = 80
        for layer in range(3):
            offset = layer * 1.4
            reach = middle * 0.8 * self._energy * (1 - layer * 0.22)
            path = QPainterPath()
            for point in range(steps + 1):
                across = point / steps
                wave = 0.6 * math.sin(across * 9 + t * 2.1 + offset)
                wave += 0.4 * math.sin(across * 17 - t * 3.3 + offset * 2)
                y = middle - wave * reach * math.sin(across * math.pi)
                if point == 0:
                    path.moveTo(0, y)
                else:
                    path.lineTo(width * across, y)
            painter.setOpacity(self._fade * (1 - layer * 0.28))
            painter.strokePath(path, QPen(self._brush(), 3))
            path.lineTo(width, middle)
            path.lineTo(0, middle)
            path.closeSubpath()
            painter.setOpacity(self._fade * 0.16)
            painter.drawPath(path)

    def _draw_circle(self, painter: QPainter, count: int) -> None:
        """Rays around a ring that breathes."""
        centre = QPointF(self.width() / 2, self.height() / 2)
        space = min(self.width(), self.height()) / 2
        breath = math.sin((time.monotonic() - self._started) / 0.7) * 0.03 * self._energy
        ring = space * (0.42 + breath)
        pen = QPen(QColor(COLOURS[0]), max(2.0, 2 * math.pi * ring / count * 0.6))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        for index in range(count):
            angle = 2 * math.pi * index / count - math.pi / 2
            reach = ring + self._levels[index] * (space - ring) * 0.86
            direction = QPointF(math.cos(angle), math.sin(angle))
            # Colours run around the ring and back, so the two ends meet without a jump.
            pen.setColor(colour_across(1 - abs(2 * index / count - 1)))
            painter.setPen(pen)
            painter.drawLine(centre + direction * ring, centre + direction * reach)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(self._fade * 0.2)
        painter.drawEllipse(centre, ring * 0.82, ring * 0.82)

    def _draw_lights(self, painter: QPainter, count: int) -> None:
        """Columns of small lights, like a stereo's display."""
        slot = self.width() / count
        rows = max(6, min(18, int(self.height() / slot)))
        cell = self.height() / rows
        size = min(slot, cell) * 0.76
        on: list[QRectF] = []
        off: list[QRectF] = []
        for column in range(count):
            lit = int(self._levels[column] * rows)
            top = int(self._peaks[column] * rows)
            x = column * slot + (slot - size) / 2
            for row in range(rows):
                y = self.height() - (row + 1) * cell + (cell - size) / 2
                (on if row < lit or row == top else off).append(QRectF(x, y, size, size))
        # Square and in two batches: many hundreds of separately drawn rounded cells took too long.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setOpacity(self._fade * 0.1)
        painter.drawRects(off)
        painter.setOpacity(self._fade)
        painter.drawRects(on)


class CoverView(QWidget):
    """The picture, as large as fits, with rounded corners and its shape kept."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(80, 80)

    def set_image(self, image: QImage | None) -> None:
        self._pixmap = QPixmap.fromImage(image) if image is not None else QPixmap()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._pixmap.isNull():
            return
        scaled = self._pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF(
            (self.width() - scaled.width()) / 2,
            (self.height() - scaled.height()) / 2,
            scaled.width(),
            scaled.height(),
        )
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(target, 14, 14)
        painter.setClipPath(clip)
        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        painter.end()


class AudioView(QFrame):
    """The player's page for audio. Everything in it comes from the file, so it's shown as plain text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("audioView")
        self._colour: QColor | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.XL, theme.XL, theme.XL, theme.L)
        box.setSpacing(theme.S)
        self.visualizer = Visualizer()
        self.cover = CoverView()
        self._art = QStackedWidget()
        self._art.addWidget(self.visualizer)
        self._art.addWidget(self.cover)
        box.addWidget(self._art, stretch=1)
        self.title = QLabel()
        self.title.setObjectName("title")
        self.artist = QLabel()
        self.artist.setObjectName("muted")
        plain_text(self.title, self.artist)
        for label in (self.title, self.artist):
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            label.setWordWrap(True)
            box.addWidget(label)
        self.title.setAccessibleName("Song title")
        self.artist.setAccessibleName("Artist")

    @property
    def showing_picture(self) -> bool:
        return self._art.currentWidget() is self.cover

    def set_details(self, title: str, artist: str) -> None:
        self.title.setText(title)
        self.artist.setText(artist)
        self.artist.setVisible(bool(artist))

    def set_picture(self, image: QImage | None) -> None:
        self.cover.set_image(image)
        self._art.setCurrentWidget(self.cover if image is not None else self.visualizer)
        self._colour = colour_from(image) if image is not None else None
        self.update()

    def set_playing(self, playing: bool) -> None:
        self.visualizer.set_playing(playing)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, self._colour or QColor(theme.SURFACE_RAISED))
        gradient.setColorAt(1, QColor(theme.BG))
        painter.fillRect(self.rect(), gradient)
        painter.end()


class QueueDialog(QDialog):
    """What plays next. Double-click or press Enter to jump to a file."""

    def __init__(self, names: list[str], current: int, on_choose, parent: QWidget | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Queue")
        self.setMinimumSize(420, 420)
        box = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setAccessibleName("Queue")
        for index, name in enumerate(names):
            item = QListWidgetItem(name)
            if index == current:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.list.addItem(item)
        if 0 <= current < self.list.count():
            self.list.setCurrentRow(current)
            self.list.scrollToItem(self.list.currentItem())
        self.list.itemActivated.connect(lambda item: self._choose(on_choose, self.list.row(item)))
        box.addWidget(self.list)

    def _choose(self, on_choose, row: int) -> None:  # type: ignore[no-untyped-def]
        on_choose(row)
        self.accept()
