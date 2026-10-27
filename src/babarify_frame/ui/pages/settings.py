"""Settings page: a small set of persisted UI preferences, fully keyboard navigable."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.configuration.preferences import SEEK_STEPS_S, Preferences
from babarify_frame.ui import theme


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


class SettingsPage(QWidget):
    preferences_changed = Signal(object)  # Preferences

    def __init__(self, prefs: Preferences, settings_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self._prefs = prefs
        self._loading = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("page")
        column = QVBoxLayout(content)
        column.setContentsMargins(theme.XXL, theme.XL, theme.XXL, theme.XL)
        column.setSpacing(theme.L)
        column.addWidget(_label("Settings", "title"))

        self.seek_step = QComboBox()
        for step in SEEK_STEPS_S:
            self.seek_step.addItem(f"{step} seconds", step)
        self.seek_step.setAccessibleName("Seek step")
        self.remember_volume = QCheckBox("Remember volume and mute between sessions")
        playback = self._card("Playback", [("Seek step (← →)", self.seek_step), ("", self.remember_volume)])

        self.hide_delay = QSpinBox()
        self.hide_delay.setRange(1, 10)
        self.hide_delay.setSuffix(" s")
        self.hide_delay.setAccessibleName("Hide controls after")
        self.start_fullscreen = QCheckBox("Switch to fullscreen when a video starts")
        fullscreen = self._card(
            "Fullscreen", [("Hide controls after", self.hide_delay), ("", self.start_fullscreen)]
        )

        privacy = self._card("Privacy", [])
        privacy_box = privacy.layout()
        assert isinstance(privacy_box, QVBoxLayout)
        privacy_box.addWidget(
            _label(
                "Babarify Frame plays files locally. It has no account, no ads and no telemetry. "
                "These settings are stored only on this PC:",
                "muted",
            )
        )
        path_label = _label(str(settings_path), "caption")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        privacy_box.addWidget(path_label)

        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.setAccessibleName("Reset settings to defaults")
        self.reset_button.clicked.connect(self._reset)

        for widget in (playback, fullscreen, privacy):
            column.addWidget(widget)
        column.addWidget(self.reset_button, alignment=Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.set_preferences(prefs)
        self.seek_step.currentIndexChanged.connect(self._changed)
        self.remember_volume.toggled.connect(self._changed)
        self.hide_delay.valueChanged.connect(self._changed)
        self.start_fullscreen.toggled.connect(self._changed)

    def _card(self, title: str, rows: list[tuple[str, QWidget]]) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(720)
        box = QVBoxLayout(card)
        box.setContentsMargins(theme.L, theme.M, theme.L, theme.L)
        box.setSpacing(theme.M)
        box.addWidget(_label(title, "subtitle"))
        if rows:
            form = QFormLayout()
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
            form.setHorizontalSpacing(theme.XL)
            form.setVerticalSpacing(theme.M)
            for text, widget in rows:
                if text:
                    form.addRow(text, widget)
                else:
                    form.addRow(widget)
            box.addLayout(form)
        return card

    @property
    def preferences(self) -> Preferences:
        return self._prefs

    def set_preferences(self, prefs: Preferences) -> None:
        self._loading = True
        self._prefs = prefs
        self.seek_step.setCurrentIndex(max(0, SEEK_STEPS_S.index(prefs.seek_step_s)))
        self.remember_volume.setChecked(prefs.remember_volume)
        self.hide_delay.setValue(round(prefs.controls_hide_delay_ms / 1000))
        self.start_fullscreen.setChecked(prefs.start_fullscreen)
        self._loading = False

    def _changed(self) -> None:
        if self._loading:
            return
        self._prefs = replace(
            self._prefs,
            seek_step_s=int(self.seek_step.currentData()),
            remember_volume=self.remember_volume.isChecked(),
            controls_hide_delay_ms=self.hide_delay.value() * 1000,
            start_fullscreen=self.start_fullscreen.isChecked(),
        ).normalized()
        self.preferences_changed.emit(self._prefs)

    def _reset(self) -> None:
        defaults = Preferences()
        self.set_preferences(replace(defaults, window=self._prefs.window))
        self.preferences_changed.emit(self._prefs)
