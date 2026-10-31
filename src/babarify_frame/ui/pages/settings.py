"""Settings page: a small set of persisted UI preferences, fully keyboard navigable."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
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

from babarify_frame.configuration.preferences import LANGUAGES, SEEK_STEPS_S, Preferences
from babarify_frame.core.models import SubtitlePosition, SubtitleStyle
from babarify_frame.ui import theme

TEXT_COLORS = {
    "#FFFFFF": "White",
    "#FFFF00": "Yellow",
    "#00FFFF": "Cyan",
    "#80FF80": "Light green",
    "#C0C0C0": "Light grey",
}
BACKGROUNDS = {0: "None (outline only)", 40: "Translucent box", 75: "Dark box", 100: "Solid box"}
POSITIONS = {
    SubtitlePosition.BOTTOM: "Bottom",
    SubtitlePosition.SLIGHTLY_RAISED: "Slightly raised",
    SubtitlePosition.RAISED: "Raised",
    SubtitlePosition.HIGH: "High",
}
_ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets", "Marlett", "Webdings", "Wingdings", "Symbol")


def installed_font_families() -> list[str]:
    return sorted(
        f for f in QFontDatabase.families() if not f.startswith("@") and not f.startswith(_ICON_FONTS)
    )


def _select(combo: QComboBox, value: object, custom_label: str) -> None:
    """Select the item whose data is ``value``; add a labelled item for values not in the list."""
    index = combo.findData(value)
    if index < 0:
        combo.addItem(custom_label, value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


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
        self.hardware_decoding = QComboBox()
        self.hardware_decoding.addItem("Automatic (recommended)", True)
        self.hardware_decoding.addItem("Off (software only)", False)
        self.hardware_decoding.setAccessibleName("Hardware decoding")
        self.hardware_decoding.setToolTip(
            "Automatic uses the graphics card when it supports the format. Changing this restarts "
            "playback at the same position."
        )
        playback = self._card(
            "Playback",
            [
                ("Seek step (← →)", self.seek_step),
                ("Hardware decoding", self.hardware_decoding),
                ("", self.remember_volume),
            ],
        )

        self.hide_delay = QSpinBox()
        self.hide_delay.setRange(1, 10)
        self.hide_delay.setSuffix(" s")
        self.hide_delay.setAccessibleName("Hide controls after")
        self.start_fullscreen = QCheckBox("Switch to fullscreen when a video starts")
        fullscreen = self._card(
            "Fullscreen", [("Hide controls after", self.hide_delay), ("", self.start_fullscreen)]
        )

        self.subtitles_auto = QCheckBox("Show subtitles automatically when a file has them")
        self.audio_language = self._language_combo("Preferred audio language")
        self.subtitle_language = self._language_combo("Preferred subtitle language")
        self.subtitle_font = QComboBox()
        self.subtitle_font.setAccessibleName("Subtitle font")
        self.subtitle_font.addItem("Default", "")
        for family in installed_font_families():
            self.subtitle_font.addItem(family, family)
        self.subtitle_font.setMaxVisibleItems(16)
        self.subtitle_size = QSpinBox()
        self.subtitle_size.setRange(50, 200)
        self.subtitle_size.setSingleStep(10)
        self.subtitle_size.setSuffix(" %")
        self.subtitle_size.setAccessibleName("Subtitle size")
        self.subtitle_color = QComboBox()
        self.subtitle_color.setAccessibleName("Subtitle colour")
        for value, name in TEXT_COLORS.items():
            self.subtitle_color.addItem(name, value)
        self.subtitle_background = QComboBox()
        self.subtitle_background.setAccessibleName("Subtitle background")
        for opacity, name in BACKGROUNDS.items():
            self.subtitle_background.addItem(name, opacity)
        self.subtitle_position = QComboBox()
        self.subtitle_position.setAccessibleName("Subtitle position")
        for position, name in POSITIONS.items():
            self.subtitle_position.addItem(name, position.value)
        self.font_warning = _label("", "warning")
        self.font_warning.hide()
        subtitles = self._card(
            "Subtitles and audio",
            [
                ("", self.subtitles_auto),
                ("Subtitle language", self.subtitle_language),
                ("Audio language", self.audio_language),
                ("Font", self.subtitle_font),
                ("", self.font_warning),
                ("Size", self.subtitle_size),
                ("Colour", self.subtitle_color),
                ("Background", self.subtitle_background),
                ("Position", self.subtitle_position),
            ],
        )
        subtitles_box = subtitles.layout()
        assert isinstance(subtitles_box, QVBoxLayout)
        subtitles_box.addWidget(
            _label(
                "The look applies to plain-text subtitles (SRT, WebVTT, MicroDVD). ASS/SSA subtitles "
                "keep the styling their author gave them. With the libVLC engine a style change restarts "
                "playback at the same position. One subtitle track is shown at a time; dual subtitles "
                "are not available yet. Subtitle files are read from this PC only and never uploaded.",
                "caption",
            )
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

        for widget in (playback, subtitles, fullscreen, privacy):
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
        self.hardware_decoding.currentIndexChanged.connect(self._changed)
        self.hide_delay.valueChanged.connect(self._changed)
        self.start_fullscreen.toggled.connect(self._changed)
        self.subtitles_auto.toggled.connect(self._changed)
        for combo in (
            self.audio_language,
            self.subtitle_language,
            self.subtitle_font,
            self.subtitle_color,
            self.subtitle_background,
            self.subtitle_position,
        ):
            combo.currentIndexChanged.connect(self._changed)
        self.subtitle_size.valueChanged.connect(self._changed)

    def _language_combo(self, accessible: str) -> QComboBox:
        combo = QComboBox()
        combo.setAccessibleName(accessible)
        for code, name in LANGUAGES.items():
            combo.addItem(name, code)
        return combo

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
        self.hardware_decoding.setCurrentIndex(0 if prefs.hardware_decoding else 1)
        self.hide_delay.setValue(round(prefs.controls_hide_delay_ms / 1000))
        self.start_fullscreen.setChecked(prefs.start_fullscreen)
        self.subtitles_auto.setChecked(prefs.subtitles_auto)
        _select(self.audio_language, prefs.preferred_audio_language, prefs.preferred_audio_language)
        _select(self.subtitle_language, prefs.preferred_subtitle_language, prefs.preferred_subtitle_language)
        style = prefs.subtitle_style
        missing = bool(style.font_family) and self.subtitle_font.findData(style.font_family) < 0
        _select(self.subtitle_font, style.font_family, f"{style.font_family} (not installed)")
        self.font_warning.setText(
            f"“{style.font_family}” is not installed on this PC; the engine uses its default font."
        )
        self.font_warning.setVisible(missing)
        self.subtitle_size.setValue(style.size_pct)
        _select(self.subtitle_color, style.text_color, f"Custom ({style.text_color})")
        _select(self.subtitle_background, style.background_opacity, f"Custom ({style.background_opacity} %)")
        _select(self.subtitle_position, style.position.value, style.position.value)
        self._loading = False

    def _changed(self) -> None:
        if self._loading:
            return
        self._prefs = replace(
            self._prefs,
            seek_step_s=int(self.seek_step.currentData()),
            remember_volume=self.remember_volume.isChecked(),
            hardware_decoding=bool(self.hardware_decoding.currentData()),
            controls_hide_delay_ms=self.hide_delay.value() * 1000,
            start_fullscreen=self.start_fullscreen.isChecked(),
            subtitles_auto=self.subtitles_auto.isChecked(),
            preferred_audio_language=str(self.audio_language.currentData()),
            preferred_subtitle_language=str(self.subtitle_language.currentData()),
            subtitle_style=SubtitleStyle(
                font_family=str(self.subtitle_font.currentData()),
                size_pct=self.subtitle_size.value(),
                text_color=str(self.subtitle_color.currentData()),
                background_opacity=int(self.subtitle_background.currentData()),
                position=SubtitlePosition(self.subtitle_position.currentData()),
            ),
        ).normalized()
        self.font_warning.setVisible(self.subtitle_font.currentText().endswith("(not installed)"))
        self.preferences_changed.emit(self._prefs)

    def _reset(self) -> None:
        defaults = Preferences()
        self.set_preferences(replace(defaults, window=self._prefs.window))
        self.preferences_changed.emit(self._prefs)
