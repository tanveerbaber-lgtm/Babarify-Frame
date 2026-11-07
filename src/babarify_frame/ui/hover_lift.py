"""Buttons rise when the pointer is over them: a soft shadow grows under them and they sink a little when
pressed. With Windows set to show no animations, the change happens at once."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QGraphicsDropShadowEffect,
    QRadioButton,
    QWidget,
)

from babarify_frame.ui import theme
from babarify_frame.ui.audio_view import animations_allowed

DURATION_MS = 160
RAISED_BLUR = 18.0
RAISED_OFFSET = 4.0
PRESSED_OFFSET = 1.0


class HoverLift(QObject):
    """Installed once on the application; it watches every push and tool button."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._animations: dict[int, QVariantAnimation] = {}
        self._animate = animations_allowed()

    @staticmethod
    def applies_to(widget: QObject) -> bool:
        """Push and tool buttons, unless they already draw an effect of their own."""
        if not isinstance(widget, QAbstractButton) or isinstance(widget, (QCheckBox, QRadioButton)):
            return False
        effect = widget.graphicsEffect()
        return effect is None or isinstance(effect, QGraphicsDropShadowEffect)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.applies_to(watched):
            return False
        kind = event.type()
        if kind == QEvent.Type.Enter and watched.isEnabled():  # type: ignore[attr-defined]
            self._move(watched, 1.0)  # type: ignore[arg-type]
        elif kind in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.EnabledChange):
            self._move(watched, 0.0)  # type: ignore[arg-type]
        elif kind == QEvent.Type.MouseButtonPress:
            self._move(watched, 0.25)  # type: ignore[arg-type]
        elif kind == QEvent.Type.MouseButtonRelease:
            self._move(watched, 1.0 if watched.underMouse() else 0.0)  # type: ignore[attr-defined, arg-type]
        return False

    def _move(self, widget: QWidget, target: float) -> None:
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            if target == 0.0:
                return
            effect = QGraphicsDropShadowEffect(widget)
            effect.setBlurRadius(0)
            effect.setOffset(0, 0)
            widget.setGraphicsEffect(effect)
        key = id(widget)
        running = self._animations.pop(key, None)
        start = running.currentValue() if running is not None else self._height(effect)
        if running is not None:
            running.stop()
        if not self._animate:
            self._show(widget, effect, target)
            return
        animation = QVariantAnimation(widget)
        animation.setDuration(DURATION_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(float(start or 0.0))
        animation.setEndValue(target)
        animation.valueChanged.connect(lambda value: self._show(widget, effect, float(value)))
        animation.finished.connect(lambda: self._animations.pop(key, None))
        self._animations[key] = animation
        animation.start()

    @staticmethod
    def _height(effect: QGraphicsDropShadowEffect) -> float:
        return min(1.0, effect.blurRadius() / RAISED_BLUR)

    @staticmethod
    def _show(widget: QWidget, effect: QGraphicsDropShadowEffect, height: float) -> None:
        if height <= 0.0:
            widget.setGraphicsEffect(None)  # type: ignore[arg-type]  # nothing to draw while it rests
            return
        # Dark themes glow with the accent; a light theme casts an ordinary shadow.
        colour = QColor(0, 0, 0, 90) if theme.is_light() else QColor(theme.CYAN)
        if not theme.is_light():
            colour.setAlpha(150)
        effect.setColor(colour)
        effect.setBlurRadius(RAISED_BLUR * height)
        effect.setOffset(0, (RAISED_OFFSET if height > 0.3 else PRESSED_OFFSET) * height)


def install(app: QApplication) -> HoverLift:
    lift = HoverLift(app)
    app.installEventFilter(lift)
    return lift
