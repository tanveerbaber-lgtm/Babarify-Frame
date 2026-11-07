"""Buttons rise under the pointer and settle again."""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QPushButton,
)
from pytestqt.qtbot import QtBot

from babarify_frame.ui import hover_lift


def test_a_button_rises_under_the_pointer_and_settles(qtbot: QtBot) -> None:
    lift = hover_lift.HoverLift()
    lift._animate = False  # the same steps, without waiting for frames
    button = QPushButton("Play")
    qtbot.addWidget(button)
    button.show()
    lift.eventFilter(button, QEvent(QEvent.Type.Enter))
    effect = button.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert effect.blurRadius() == hover_lift.RAISED_BLUR
    assert effect.offset().y() == hover_lift.RAISED_OFFSET
    lift.eventFilter(button, QEvent(QEvent.Type.MouseButtonPress))
    assert button.graphicsEffect().offset().y() < hover_lift.RAISED_OFFSET, "sinks when pressed"
    lift.eventFilter(button, QEvent(QEvent.Type.Leave))
    assert button.graphicsEffect() is None, "nothing left drawing at rest"


def test_it_leaves_other_widgets_and_effects_alone(qtbot: QtBot) -> None:
    lift = hover_lift.HoverLift()
    lift._animate = False
    box = QCheckBox("Option")
    faded = QPushButton("Faded")
    faded.setGraphicsEffect(QGraphicsOpacityEffect(faded))
    off = QPushButton("Off")
    off.setEnabled(False)
    for widget in (box, faded, off):
        qtbot.addWidget(widget)
        lift.eventFilter(widget, QEvent(QEvent.Type.Enter))
    assert box.graphicsEffect() is None
    assert isinstance(faded.graphicsEffect(), QGraphicsOpacityEffect)
    assert off.graphicsEffect() is None


def test_the_rise_is_animated_when_windows_allows(qtbot: QtBot) -> None:
    lift = hover_lift.HoverLift()
    lift._animate = True
    button = QPushButton("Play")
    qtbot.addWidget(button)
    lift.eventFilter(button, QEvent(QEvent.Type.Enter))
    qtbot.waitUntil(lambda: button.graphicsEffect().blurRadius() == hover_lift.RAISED_BLUR, timeout=2000)
    assert QApplication.instance() is not None
