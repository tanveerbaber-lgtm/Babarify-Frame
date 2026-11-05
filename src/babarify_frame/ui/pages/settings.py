"""Settings page: a small set of persisted UI preferences, fully keyboard navigable."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.ai.models import MODELS, ModelStatus
from babarify_frame.configuration.preferences import LANGUAGES, SEEK_STEPS_S, Preferences
from babarify_frame.core.models import SubtitlePosition, SubtitleStyle
from babarify_frame.core.music import STYLE_LABELS
from babarify_frame.core.themes import THEMES
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import plain_text

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


def theme_swatch(start: str, end: str) -> QIcon:
    """A theme's colours, beside its name in the list."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 16, 16)
    gradient.setColorAt(0, QColor(start))
    gradient.setColorAt(1, QColor(end))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(0, 0, 16, 16, 4, 4)
    painter.end()
    return QIcon(pixmap)


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


class SettingsPage(QWidget):
    preferences_changed = Signal(object)  # Preferences
    clear_history_requested = Signal()
    hidden_files_requested = Signal()
    backup_requested = Signal()
    restore_requested = Signal()
    # Local AI (M9): the window does the work and reports back with set_ai_status()
    download_model_requested = Signal(str)
    delete_model_requested = Signal(str)
    delete_generated_requested = Signal()

    def __init__(
        self,
        prefs: Preferences,
        settings_path: Path,
        parent: QWidget | None = None,
        library_path: Path | None = None,
    ) -> None:
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
        self.allow_boost = QCheckBox("Allow volume above 100 % (up to 200 %)")
        self.allow_boost.setToolTip(
            "Boost makes quiet files louder but can distort loud passages. A boosted volume is "
            "never remembered: the next session starts at 100 % or less."
        )
        self.seek_previews = QCheckBox("Show pictures when pointing at the seek bar")
        self.seek_previews.setToolTip(
            "Local video files only. Pictures are made by a second, silent decoder; turn this off "
            "on slow computers."
        )
        self.hardware_decoding = QComboBox()
        self.hardware_decoding.addItem("Automatic (recommended)", True)
        self.hardware_decoding.addItem("Off (software only)", False)
        self.hardware_decoding.setAccessibleName("Hardware decoding")
        self.hardware_decoding.setToolTip(
            "Automatic uses the graphics card when it supports the format. Changing this restarts "
            "playback at the same position."
        )
        self.visual_style = QComboBox()
        for style, label in STYLE_LABELS.items():
            self.visual_style.addItem(label, style.value)
        self.visual_style.setAccessibleName("Animation for audio with no picture")
        self.visual_style.setToolTip(
            "Decoration for songs with no picture of their own. It doesn't follow the sound."
        )
        self.colour_theme = QComboBox()
        self.colour_theme.setAccessibleName("Colour theme")
        for key, palette in THEMES.items():
            self.colour_theme.addItem(theme_swatch(palette.accent, palette.accent2), palette.label, key)
        self.show_status_bar = QCheckBox("Show the status bar at the bottom of the window")
        self.show_status_bar.setToolTip(
            "Technical details and short messages. Playback info (Ctrl+I) has the same details."
        )
        appearance = self._card(
            "Appearance",
            [
                ("Colour theme", self.colour_theme),
                ("Animation for audio with no picture", self.visual_style),
                ("", self.show_status_bar),
            ],
        )
        playback = self._card(
            "Playback",
            [
                ("Seek step (← →)", self.seek_step),
                ("Hardware decoding", self.hardware_decoding),
                ("", self.remember_volume),
                ("", self.allow_boost),
                ("", self.seek_previews),
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
        plain_text(self.font_warning)  # the font name comes from the settings file
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

        self.remember_history = QCheckBox("Remember recently played files and where I stopped")
        self.resume_playback = QCheckBox("Resume files where I left off")
        self.clear_history_button = QPushButton("Clear history…")
        self.clear_history_button.setAccessibleName("Clear playback history")
        self.clear_history_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.clear_history_button.clicked.connect(self.clear_history_requested)
        self.hidden_files_button = QPushButton("Hidden files…")
        self.hidden_files_button.setAccessibleName("Hidden files in the library")
        self.hidden_files_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.hidden_files_button.clicked.connect(self.hidden_files_requested)
        self.backup_button = QPushButton("Back up settings and playlists…")
        self.backup_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.backup_button.clicked.connect(self.backup_requested)
        self.restore_button = QPushButton("Restore from a backup…")
        self.restore_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.restore_button.clicked.connect(self.restore_requested)
        privacy = self._card(
            "Privacy",
            [
                ("", self.remember_history),
                ("", self.resume_playback),
                ("", self.hidden_files_button),
                ("", self.clear_history_button),
                ("", self.backup_button),
                ("", self.restore_button),
            ],
        )
        privacy_box = privacy.layout()
        assert isinstance(privacy_box, QVBoxLayout)
        privacy_box.addWidget(
            _label(
                "Babarify Media Player plays files locally. It has no account, no ads and no telemetry. "
                "Settings, history, the library and its thumbnails are stored only on this PC:",
                "muted",
            )
        )
        locations = [str(settings_path)] + ([str(library_path)] if library_path is not None else [])
        path_label = _label("\n".join(locations), "caption")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        privacy_box.addWidget(path_label)

        ai = self._build_ai_card()

        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.setAccessibleName("Reset settings to defaults")
        self.reset_button.clicked.connect(self._reset)

        for widget in (appearance, playback, subtitles, fullscreen, privacy, ai):
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
        self.allow_boost.toggled.connect(self._changed)
        self.seek_previews.toggled.connect(self._changed)
        self.hardware_decoding.currentIndexChanged.connect(self._changed)
        self.visual_style.currentIndexChanged.connect(self._changed)
        self.colour_theme.currentIndexChanged.connect(self._changed)
        self.show_status_bar.toggled.connect(self._changed)
        self.hide_delay.valueChanged.connect(self._changed)
        self.start_fullscreen.toggled.connect(self._changed)
        self.subtitles_auto.toggled.connect(self._changed)
        self.remember_history.toggled.connect(self._changed)
        self.resume_playback.toggled.connect(self._changed)
        self.ai_enabled.toggled.connect(self._changed)
        self.ai_model.currentIndexChanged.connect(self._changed)
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

    def _build_ai_card(self) -> QFrame:
        self.ai_enabled = QCheckBox("Turn on AI features (they run on this PC)")
        self.ai_missing = _label(
            "The local AI component is not installed. To add it, run the Babarify Media Player installer "
            "again and choose the full installation.",
            "warning",
        )
        self.ai_model = QComboBox()
        self.ai_model.setAccessibleName("Speech model")
        for name, model in MODELS.items():
            self.ai_model.addItem(f"{model.label} · {model.size / 1e6:.0f} MB", name)
        self.ai_model_status = _label("", "muted")
        self.ai_download = QPushButton("Download…")
        self.ai_download.clicked.connect(
            lambda: self.download_model_requested.emit(self.ai_model.currentData())
        )
        self.ai_delete_model = QPushButton("Delete model")
        self.ai_delete_model.clicked.connect(
            lambda: self.delete_model_requested.emit(self.ai_model.currentData())
        )
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.ai_download)
        row.addWidget(self.ai_delete_model)
        row.addWidget(self.ai_model_status, stretch=1)
        self.ai_generated = _label("", "muted")
        self.ai_delete_generated = QPushButton("Delete all generated subtitles…")
        self.ai_delete_generated.clicked.connect(self.delete_generated_requested)
        self.ai_delete_generated.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        card = self._card(
            "AI features",
            [
                ("", self.ai_enabled),
                ("", self.ai_missing),
                ("Speech model", self.ai_model),
                ("", buttons),
                ("", self.ai_generated),
                ("", self.ai_delete_generated),
            ],
        )
        box = card.layout()
        assert isinstance(box, QVBoxLayout)
        box.addWidget(
            _label(
                "Generate subtitles from speech (Audio & Subtitles → Generate subtitles) and search what "
                "is said in them. Everything runs on this PC with open-source Whisper models "
                "(MIT licence); media, sound and subtitles are never uploaded. The only network use is "
                "downloading a model, after you confirm. Generated subtitles are marked "
                "machine-generated and kept in Babarify's own folder, not next to your files.",
                "caption",
            )
        )
        return card

    def set_ai_status(
        self,
        statuses: dict[str, ModelStatus],
        generated: int,
        generated_bytes: int,
        busy: str = "",
        installed: bool = True,
    ) -> None:
        """Model and generated-subtitle state, refreshed by the window."""
        self.ai_missing.setVisible(not installed)
        self.ai_enabled.setEnabled(installed or self.ai_enabled.isChecked())  # can always switch off
        for widget in (self.ai_model, self.ai_download, self.ai_delete_model):
            widget.setVisible(installed)
        name = str(self.ai_model.currentData())
        state = statuses.get(name, ModelStatus.MISSING)
        text = {
            ModelStatus.INSTALLED: "Installed",
            ModelStatus.MISSING: "Not downloaded",
            ModelStatus.DAMAGED: "Damaged: delete and download again",
        }[state]
        self.ai_model_status.setText(busy or text)
        self.ai_download.setEnabled(not busy and state is not ModelStatus.INSTALLED)
        self.ai_delete_model.setEnabled(not busy and state is not ModelStatus.MISSING)
        self.ai_generated.setText(
            f"Generated subtitles: {generated} file{'s' if generated != 1 else ''}"
            + (f" ({generated_bytes / 1024:.0f} KB)" if generated else "")
        )
        self.ai_delete_generated.setEnabled(generated > 0)

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
        self.allow_boost.setChecked(prefs.allow_volume_boost)
        self.seek_previews.setChecked(prefs.seek_previews)
        self.hardware_decoding.setCurrentIndex(0 if prefs.hardware_decoding else 1)
        self.visual_style.setCurrentIndex(max(0, self.visual_style.findData(prefs.visual_style)))
        self.colour_theme.setCurrentIndex(max(0, self.colour_theme.findData(prefs.colour_theme)))
        self.show_status_bar.setChecked(prefs.show_status_bar)
        self.hide_delay.setValue(round(prefs.controls_hide_delay_ms / 1000))
        self.start_fullscreen.setChecked(prefs.start_fullscreen)
        self.subtitles_auto.setChecked(prefs.subtitles_auto)
        self.remember_history.setChecked(prefs.remember_history)
        self.resume_playback.setChecked(prefs.resume_playback)
        self.resume_playback.setEnabled(prefs.remember_history)
        self.ai_enabled.setChecked(prefs.ai_enabled)
        self.ai_model.setCurrentIndex(max(0, self.ai_model.findData(prefs.ai_model)))
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
            allow_volume_boost=self.allow_boost.isChecked(),
            seek_previews=self.seek_previews.isChecked(),
            hardware_decoding=bool(self.hardware_decoding.currentData()),
            visual_style=str(self.visual_style.currentData()),
            colour_theme=str(self.colour_theme.currentData()),
            show_status_bar=self.show_status_bar.isChecked(),
            controls_hide_delay_ms=self.hide_delay.value() * 1000,
            start_fullscreen=self.start_fullscreen.isChecked(),
            subtitles_auto=self.subtitles_auto.isChecked(),
            remember_history=self.remember_history.isChecked(),
            resume_playback=self.resume_playback.isChecked(),
            ai_enabled=self.ai_enabled.isChecked(),
            ai_model=str(self.ai_model.currentData()),
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
        self.resume_playback.setEnabled(self.remember_history.isChecked())
        self.preferences_changed.emit(self._prefs)

    def _reset(self) -> None:
        defaults = Preferences()
        self.set_preferences(replace(defaults, window=self._prefs.window))
        self.preferences_changed.emit(self._prefs)
