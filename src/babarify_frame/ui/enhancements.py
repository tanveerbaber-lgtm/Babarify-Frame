"""Picture & Sound panel (M7): picture adjustments, aspect/crop/zoom/rotation, equalizer, profiles.

Every control is built from the engine's capabilities: anything the engine reports as
unsupported is disabled and says why. Changes apply immediately; rotation on libVLC restarts
playback at the same position (capability ``rotation == "restart"``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.core.enhancements import (
    ASPECT_RATIOS,
    EQ_BAND_COUNT,
    EQ_BAND_MAX_DB,
    EQ_BAND_MIN_DB,
    MAX_PROFILE_NAME,
    MAX_PROFILES,
    PICTURE_RANGES,
    TRANSFORM_LABELS,
    ZOOM_LEVELS,
    EnhancementProfile,
    EqualizerSettings,
    PictureSettings,
    VideoTransform,
)
from babarify_frame.core.models import EngineCapabilities
from babarify_frame.ui import theme

# name: (label, slider scale, unit). Slider ints = value * scale.
PICTURE_CONTROLS: dict[str, tuple[str, int, str]] = {
    "brightness": ("Brightness", 100, "%"),
    "contrast": ("Contrast", 100, "%"),
    "saturation": ("Saturation", 100, "%"),
    "hue": ("Hue", 1, "°"),
    "gamma": ("Gamma", 100, "%"),
}
ZOOM_LABELS = {0.0: "Fit window", 0.5: "50 %", 1.0: "100 % (actual pixels)", 2.0: "200 %"}
CUSTOM = "Custom"


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("caption")
    label.setWordWrap(True)
    return label


def band_label(hz: int) -> str:
    return f"{hz // 1000}k" if hz >= 1000 else str(hz)


class EnhancementsDialog(QDialog):
    picture_changed = Signal(object)  # PictureSettings
    equalizer_changed = Signal(object)  # EqualizerSettings
    geometry_changed = Signal(str, str, float)  # aspect, crop, zoom
    transform_changed = Signal(object)  # VideoTransform
    profiles_changed = Signal(object)  # tuple[EnhancementProfile, ...]

    def __init__(
        self,
        preset_values: Callable[[str], EqualizerSettings],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Picture & Sound")
        self.setModal(False)
        self.setMinimumWidth(560)
        self._preset_values = preset_values
        self._loading = False
        self._caps: EngineCapabilities | None = None
        self._profiles: tuple[EnhancementProfile, ...] = ()
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._picture_tab(), "Picture")
        self.tabs.addTab(self._video_tab(), "Video")
        self.tabs.addTab(self._audio_tab(), "Audio")
        self.tabs.addTab(self._profiles_tab(), "Profiles")
        box.addWidget(self.tabs)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        box.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------ picture
    def _picture_tab(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.M)
        self.picture_sliders: dict[str, QSlider] = {}
        self.picture_values: dict[str, QLabel] = {}
        self.picture_resets: dict[str, QPushButton] = {}
        for row, (name, (text, scale, _unit)) in enumerate(PICTURE_CONTROLS.items()):
            default, low, high = PICTURE_RANGES[name]
            label = QLabel(text)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(round(low * scale), round(high * scale))
            slider.setValue(round(default * scale))
            slider.setPageStep(10)
            slider.setAccessibleName(text)
            value = QLabel()
            value.setMinimumWidth(56)
            reset = QPushButton("Reset")
            reset.setAccessibleName(f"Reset {text.lower()}")
            label.setBuddy(slider)
            slider.valueChanged.connect(self._picture_edited)
            reset.clicked.connect(lambda _=False, s=slider, d=default, k=scale: s.setValue(round(d * k)))
            for col, widget in enumerate((label, slider, value, reset)):
                grid.addWidget(widget, row, col)
            self.picture_sliders[name] = slider
            self.picture_values[name] = value
            self.picture_resets[name] = reset
        box.addLayout(grid)
        self.picture_note = _caption("")
        box.addWidget(self.picture_note)
        self.reset_picture_button = QPushButton("Reset picture")
        self.reset_picture_button.clicked.connect(lambda: self.set_picture(PictureSettings(), emit=True))
        box.addWidget(self.reset_picture_button, alignment=Qt.AlignmentFlag.AlignLeft)
        box.addStretch(1)
        self._show_picture_values()
        return page

    def picture(self) -> PictureSettings:
        values = {
            name: slider.value() / PICTURE_CONTROLS[name][1] for name, slider in self.picture_sliders.items()
        }
        return PictureSettings(**values).normalized()

    def set_picture(self, picture: PictureSettings, emit: bool = False) -> None:
        self._loading = True
        for name, slider in self.picture_sliders.items():
            slider.setValue(round(getattr(picture, name) * PICTURE_CONTROLS[name][1]))
        self._loading = False
        self._show_picture_values()
        if emit:
            self.picture_changed.emit(self.picture())

    def _show_picture_values(self) -> None:
        for name, slider in self.picture_sliders.items():
            _text, _scale, unit = PICTURE_CONTROLS[name]
            self.picture_values[name].setText(f"{slider.value()} {unit}")

    def _picture_edited(self) -> None:
        self._show_picture_values()
        if not self._loading:
            self.picture_changed.emit(self.picture())

    # -------------------------------------------------------------- video
    def _video_tab(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        form = QFormLayout()
        self.aspect = QComboBox()
        self.crop = QComboBox()
        for combo, first in ((self.aspect, "As in the file"), (self.crop, "No crop")):
            for ratio in ASPECT_RATIOS:
                combo.addItem(ratio or first, ratio)
        self.zoom = QComboBox()
        for level in ZOOM_LEVELS:
            self.zoom.addItem(ZOOM_LABELS[level], level)
        self.rotation = QComboBox()
        for transform, text in TRANSFORM_LABELS.items():
            self.rotation.addItem(text, transform.value)
        for text, combo in (
            ("Aspect ratio", self.aspect),
            ("Crop to", self.crop),
            ("Zoom", self.zoom),
            ("Rotate or flip", self.rotation),
        ):
            combo.setAccessibleName(text)
            form.addRow(text, combo)
        box.addLayout(form)
        self.video_note = _caption("")
        box.addWidget(self.video_note)
        box.addWidget(
            _caption(
                "Aspect, crop and zoom apply to the current file and reset when another file opens. "
                "Rotation stays until you change it or close the app. Rotating decodes every frame on "
                "the processor: 4K video may stutter (measured in M7: about two thirds of the frames "
                "dropped on the test PC)."
            )
        )
        box.addStretch(1)
        for combo in (self.aspect, self.crop, self.zoom):
            combo.currentIndexChanged.connect(self._geometry_edited)
        self.rotation.currentIndexChanged.connect(self._rotation_edited)
        return page

    def set_video(self, geometry: tuple[str, str, float], transform: VideoTransform) -> None:
        self._loading = True
        aspect, crop, zoom = geometry
        self.aspect.setCurrentIndex(max(0, self.aspect.findData(aspect)))
        self.crop.setCurrentIndex(max(0, self.crop.findData(crop)))
        self.zoom.setCurrentIndex(max(0, self.zoom.findData(zoom)))
        self.rotation.setCurrentIndex(max(0, self.rotation.findData(transform.value)))
        self._loading = False

    def _geometry_edited(self) -> None:
        if not self._loading:
            self.geometry_changed.emit(
                str(self.aspect.currentData()), str(self.crop.currentData()), float(self.zoom.currentData())
            )

    def _rotation_edited(self) -> None:
        if not self._loading:
            self.transform_changed.emit(VideoTransform(self.rotation.currentData()))

    # -------------------------------------------------------------- audio
    def _audio_tab(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        top = QHBoxLayout()
        self.eq_enabled = QCheckBox("Equalizer on")
        self.eq_preset = QComboBox()
        self.eq_preset.setAccessibleName("Equalizer preset")
        top.addWidget(self.eq_enabled)
        top.addStretch(1)
        top.addWidget(QLabel("Preset"))
        top.addWidget(self.eq_preset)
        box.addLayout(top)
        bands = QGridLayout()
        self.eq_sliders: list[QSlider] = []
        self.eq_labels: list[QLabel] = []
        self.preamp = self._eq_slider("Preamp")
        bands.addWidget(self.preamp, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)
        preamp_label = QLabel("Pre")
        bands.addWidget(preamp_label, 1, 0, alignment=Qt.AlignmentFlag.AlignHCenter)
        for i in range(EQ_BAND_COUNT):
            slider = self._eq_slider(f"Band {i + 1}")
            label = QLabel("")
            bands.addWidget(slider, 0, i + 1, alignment=Qt.AlignmentFlag.AlignHCenter)
            bands.addWidget(label, 1, i + 1, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.eq_sliders.append(slider)
            self.eq_labels.append(label)
        box.addLayout(bands)
        box.addWidget(
            _caption(
                f"Each band: {EQ_BAND_MIN_DB:+.0f} to {EQ_BAND_MAX_DB:+.0f} dB. Raising bands or the "
                "preamp can make loud passages distort; lower the preamp if that happens."
            )
        )
        self.audio_note = _caption("")
        box.addWidget(self.audio_note)
        self.reset_eq_button = QPushButton("Reset equalizer")
        self.reset_eq_button.clicked.connect(lambda: self.set_equalizer(EqualizerSettings(), emit=True))
        box.addWidget(self.reset_eq_button, alignment=Qt.AlignmentFlag.AlignLeft)
        box.addStretch(1)
        self.eq_enabled.toggled.connect(self._eq_edited)
        self.eq_preset.activated.connect(self._preset_chosen)
        return page

    def _eq_slider(self, name: str) -> QSlider:
        slider = QSlider(Qt.Orientation.Vertical)
        slider.setRange(round(EQ_BAND_MIN_DB), round(EQ_BAND_MAX_DB))
        slider.setValue(0)
        slider.setMinimumHeight(140)
        slider.setAccessibleName(f"{name} in decibels")
        slider.valueChanged.connect(lambda _v: self._eq_edited(custom=True))
        return slider

    def equalizer(self) -> EqualizerSettings:
        preset = self.eq_preset.currentText()
        return EqualizerSettings(
            enabled=self.eq_enabled.isChecked(),
            preset="" if preset == CUSTOM else preset,
            preamp_db=float(self.preamp.value()),
            bands_db=tuple(float(s.value()) for s in self.eq_sliders),
        )

    def set_equalizer(self, equalizer: EqualizerSettings, emit: bool = False) -> None:
        self._loading = True
        self.eq_enabled.setChecked(equalizer.enabled)
        self.preamp.setValue(round(equalizer.preamp_db))
        for slider, value in zip(self.eq_sliders, equalizer.bands_db, strict=False):
            slider.setValue(round(value))
        index = self.eq_preset.findText(equalizer.preset) if equalizer.preset else -1
        self.eq_preset.setCurrentIndex(index if index >= 0 else max(0, self.eq_preset.findText(CUSTOM)))
        self._loading = False
        self._update_eq_enabled()
        if emit:
            self.equalizer_changed.emit(self.equalizer())

    def _preset_chosen(self) -> None:
        name = self.eq_preset.currentText()
        if name == CUSTOM:
            return
        values = self._preset_values(name)
        self.set_equalizer(replace(values, enabled=True), emit=True)

    def _eq_edited(self, custom: bool = False) -> None:
        if self._loading:
            return
        if custom:
            self._loading = True
            self.eq_preset.setCurrentIndex(max(0, self.eq_preset.findText(CUSTOM)))
            self._loading = False
        self._update_eq_enabled()
        self.equalizer_changed.emit(self.equalizer())

    def _update_eq_enabled(self) -> None:
        supported = bool(self._caps and self._caps.supports_equalizer)
        on = supported and self.eq_enabled.isChecked()
        for slider in (self.preamp, *self.eq_sliders):
            slider.setEnabled(on)

    # ----------------------------------------------------------- profiles
    def _profiles_tab(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(_caption("A profile saves the current picture and equalizer settings under a name."))
        self.profile_list = QListWidget()
        self.profile_list.setAccessibleName("Saved profiles")
        box.addWidget(self.profile_list, stretch=1)
        row = QHBoxLayout()
        self.save_profile_button = QPushButton("Save current as…")
        self.apply_profile_button = QPushButton("Apply")
        self.delete_profile_button = QPushButton("Delete")
        self.reset_all_button = QPushButton("Reset all to defaults")
        for button in (self.save_profile_button, self.apply_profile_button, self.delete_profile_button):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.reset_all_button)
        box.addLayout(row)
        self.save_profile_button.clicked.connect(lambda: self.save_profile())
        self.apply_profile_button.clicked.connect(self.apply_selected_profile)
        self.delete_profile_button.clicked.connect(self.delete_selected_profile)
        self.reset_all_button.clicked.connect(self.reset_all)
        self.profile_list.itemActivated.connect(lambda _i: self.apply_selected_profile())
        self.profile_list.currentRowChanged.connect(lambda _r: self._update_profile_buttons())
        return page

    def set_profiles(self, profiles: tuple[EnhancementProfile, ...]) -> None:
        self._profiles = profiles
        self.profile_list.clear()
        for profile in profiles:
            item = QListWidgetItem(profile.name)
            self.profile_list.addItem(item)
        self._update_profile_buttons()

    def _update_profile_buttons(self) -> None:
        selected = self.profile_list.currentRow() >= 0
        self.apply_profile_button.setEnabled(selected)
        self.delete_profile_button.setEnabled(selected)

    def save_profile(self, name: str | None = None) -> EnhancementProfile | None:
        if name is None:
            name, ok = QInputDialog.getText(self, "Save profile", "Profile name:")
            if not ok:
                return None
        clean = " ".join(name.split())[:MAX_PROFILE_NAME]
        if not clean:
            return None
        existing = [p for p in self._profiles if p.name.casefold() != clean.casefold()]
        if len(existing) >= MAX_PROFILES:
            QMessageBox.information(self, "Profiles", f"You can keep up to {MAX_PROFILES} profiles.")
            return None
        profile = EnhancementProfile(clean, self.picture(), self.equalizer())
        self.set_profiles((*existing, profile))
        self.profile_list.setCurrentRow(self.profile_list.count() - 1)
        self.profiles_changed.emit(self._profiles)
        return profile

    def apply_selected_profile(self) -> None:
        row = self.profile_list.currentRow()
        if 0 <= row < len(self._profiles):
            profile = self._profiles[row]
            self.set_picture(profile.picture, emit=True)
            if self._caps is not None and self._caps.supports_equalizer:
                self.set_equalizer(profile.equalizer, emit=True)

    def delete_selected_profile(self) -> None:
        row = self.profile_list.currentRow()
        if 0 <= row < len(self._profiles):
            self.set_profiles(tuple(p for i, p in enumerate(self._profiles) if i != row))
            self.profiles_changed.emit(self._profiles)

    def reset_all(self) -> None:
        self.set_picture(PictureSettings(), emit=True)
        if self._caps is not None and self._caps.supports_equalizer:
            self.set_equalizer(EqualizerSettings(), emit=True)
        self.set_video(("", "", 0.0), VideoTransform(self.rotation.currentData()))
        self.geometry_changed.emit("", "", 0.0)
        if self.rotation.currentData() != VideoTransform.NONE.value:
            self.rotation.setCurrentIndex(0)  # emits transform_changed

    # ------------------------------------------------------- capabilities
    def set_capabilities(self, caps: EngineCapabilities | None, has_video: bool) -> None:
        """Enable what the engine supports; explain the rest."""
        self._caps = caps
        name = caps.engine_name if caps else "the playback engine"
        picture_ok = caps.picture_adjustments if caps else frozenset()
        missing = [PICTURE_CONTROLS[n][0].lower() for n in PICTURE_CONTROLS if n not in picture_ok]
        for control, slider in self.picture_sliders.items():
            supported = control in picture_ok
            slider.setEnabled(supported)
            self.picture_resets[control].setEnabled(supported)
            slider.setToolTip("" if supported else f"Not available with {name} in the current setup")
        notes = []
        if caps is None:
            notes.append("Start the playback engine to adjust the picture.")
        elif missing:
            reason = (
                " (it has no effect with hardware decoding; turn hardware decoding off in Settings to use it)"
                if missing == ["gamma"] and caps.engine_name.lower().startswith("libvlc")
                else ""
            )
            notes.append(f"Not available here: {', '.join(missing)}{reason}.")
        if caps is not None and not has_video:
            notes.append("Changes show when a video plays.")
        self.picture_note.setText(" ".join(notes))
        self.picture_note.setVisible(bool(notes))

        video_notes = []
        for combo, supported, what in (
            (self.aspect, bool(caps and caps.supports_aspect_ratio), "aspect ratio"),
            (self.crop, bool(caps and caps.supports_crop), "crop"),
            (self.zoom, bool(caps and caps.supports_zoom), "zoom"),
        ):
            combo.setEnabled(supported)
            if not supported and caps is not None:
                video_notes.append(f"{what} is not supported by {name}")
        rotation = caps.rotation if caps else "unsupported"
        self.rotation.setEnabled(rotation != "unsupported")
        if rotation == "restart":
            video_notes.append("changing rotation briefly restarts playback at the same position")
        elif rotation == "unsupported" and caps is not None:
            video_notes.append(f"rotation is not supported by {name}")
        self.video_note.setText(("; ".join(video_notes) + ".").capitalize() if video_notes else "")
        self.video_note.setVisible(bool(video_notes))

        eq_ok = bool(caps and caps.supports_equalizer)
        self.eq_enabled.setEnabled(eq_ok)
        self.eq_preset.setEnabled(eq_ok)
        self.reset_eq_button.setEnabled(eq_ok)
        self._loading = True
        current = self.eq_preset.currentText()
        self.eq_preset.clear()
        self.eq_preset.addItem(CUSTOM)
        for preset in caps.equalizer_presets if caps else ():
            self.eq_preset.addItem(preset)
        self.eq_preset.setCurrentIndex(max(0, self.eq_preset.findText(current)))
        bands = caps.equalizer_bands_hz if caps else ()
        for i, label in enumerate(self.eq_labels):
            label.setText(band_label(bands[i]) if i < len(bands) else "")
            self.eq_sliders[i].setToolTip(f"{bands[i]} Hz" if i < len(bands) else "")
        self._loading = False
        self._update_eq_enabled()
        self.audio_note.setText("" if eq_ok or caps is None else f"The equalizer is not supported by {name}.")
        self.audio_note.setVisible(bool(self.audio_note.text()))
