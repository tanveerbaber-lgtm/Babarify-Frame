"""Responsive playback control bar: seek row on top, transport and output controls below."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal, SignalInstance
from PySide6.QtGui import QAction, QActionGroup, QIcon, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.configuration.preferences import PLAYBACK_RATES
from babarify_frame.core.music import RepeatMode
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import SeekSlider, format_time, glyph_icon, plain_text

# Width (px) below which secondary controls are hidden, most dispensable first.
VOLUME_MIN = 1  # silence is the mute button's job
COMPACT_WIDTH = 760
NARROW_WIDTH = 540

_FALLBACK = {
    "play": QStyle.StandardPixmap.SP_MediaPlay,
    "pause": QStyle.StandardPixmap.SP_MediaPause,
    "stop": QStyle.StandardPixmap.SP_MediaStop,
    "back": QStyle.StandardPixmap.SP_MediaSeekBackward,
    "forward": QStyle.StandardPixmap.SP_MediaSeekForward,
    "volume": QStyle.StandardPixmap.SP_MediaVolume,
    "mute": QStyle.StandardPixmap.SP_MediaVolumeMuted,
    "fullscreen": QStyle.StandardPixmap.SP_TitleBarMaxButton,
    "exit_fullscreen": QStyle.StandardPixmap.SP_TitleBarNormalButton,
    "subtitles": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "shuffle": QStyle.StandardPixmap.SP_BrowserReload,
    "repeat": QStyle.StandardPixmap.SP_BrowserReload,
    "repeat_one": QStyle.StandardPixmap.SP_BrowserReload,
    "previous": QStyle.StandardPixmap.SP_MediaSkipBackward,
    "next": QStyle.StandardPixmap.SP_MediaSkipForward,
    "queue": QStyle.StandardPixmap.SP_FileDialogListView,
    "heart": QStyle.StandardPixmap.SP_DialogYesButton,
    "heart_filled": QStyle.StandardPixmap.SP_DialogYesButton,
}
REPEAT_NAMES = {
    RepeatMode.OFF: "Repeat is off",
    RepeatMode.ONE: "Repeating this file",
    RepeatMode.ALL: "Repeating all",
}


def icon(widget: QWidget, name: str, color: str | None = None) -> QIcon:
    return glyph_icon(name, color or theme.TEXT, theme.TEXT_DISABLED) or widget.style().standardIcon(
        _FALLBACK[name]
    )


def rate_label(rate: float) -> str:
    return f"{rate:g}×"  # noqa: RUF001  (typographic multiplication sign is intended)


class ControlBar(QFrame):
    play_clicked = Signal()
    stop_clicked = Signal()
    back_clicked = Signal()
    forward_clicked = Signal()
    seek_requested = Signal(int)
    volume_changed = Signal(int)
    mute_clicked = Signal()
    rate_selected = Signal(float)
    fullscreen_clicked = Signal()
    tracks_menu_opening = Signal(QMenu)  # fill the menu from the current tracks
    previous_clicked = Signal()
    next_clicked = Signal()
    shuffle_clicked = Signal()
    repeat_clicked = Signal()
    queue_clicked = Signal()
    favourite_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("controlBar")
        self._plain_icons: list[tuple[QToolButton, str]] = []  # drawn again when the theme changes
        self._playing = self._muted = self._fullscreen = self._favourite = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.L, theme.S, theme.L, theme.S)
        outer.setSpacing(theme.XS)

        # Seek row
        seek_row = QHBoxLayout()
        seek_row.setSpacing(theme.M)
        self.time_label = self._label(format_time(0), "time", "Elapsed time")
        self.seek = SeekSlider()
        self.seek.setObjectName("seek")
        self.seek.seek_requested.connect(self.seek_requested)
        self.duration_label = self._label(format_time(None), "time", "Duration")
        seek_row.addWidget(self.time_label)
        seek_row.addWidget(self.seek, stretch=1)
        seek_row.addWidget(self.duration_label)
        outer.addLayout(seek_row)

        # Button row
        row = QHBoxLayout()
        row.setSpacing(theme.S)
        self.play_button = self._button("play", "Play", "Play/Pause (Space)", self.play_clicked, size=40)
        self.play_button.setObjectName("playButton")
        self.play_button.setIcon(icon(self, "play", theme.ON_ACCENT))
        self.stop_button = self._button("stop", "Stop", "Stop (S)", self.stop_clicked)
        self.back_button = self._button("back", "Back", "Back (←)", self.back_clicked)
        self.forward_button = self._button("forward", "Forward", "Forward (→)", self.forward_clicked)
        self.previous_button = self._button("previous", "Previous", "Previous (P)", self.previous_clicked)
        self.next_button = self._button("next", "Next", "Next (N)", self.next_clicked)
        self.shuffle_button = self._button("shuffle", "Shuffle is off", "Shuffle (Z)", self.shuffle_clicked)
        self.repeat_button = self._button(
            "repeat", REPEAT_NAMES[RepeatMode.OFF], "Repeat (R)", self.repeat_clicked
        )
        self.queue_button = self._button("queue", "Queue", "Queue (Q)", self.queue_clicked)
        self.favourite_button = self._button(
            "heart", "Add to favourites", "Add to favourites (U)", self.favourite_clicked
        )
        self._has_list = False
        self._can_favourite = False
        self._repeat = RepeatMode.OFF
        self._shuffle_on = False
        self.title_label = self._label("", "mediaTitle", "Now playing")
        self.title_label.setMinimumWidth(40)
        plain_text(self.title_label)
        self.speed_button = QToolButton()
        self.speed_button.setObjectName("speedButton")
        self.speed_button.setText(rate_label(1.0))
        self.speed_button.setToolTip("Playback speed")
        self.speed_button.setAccessibleName("Playback speed")
        self.speed_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.speed_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._speed_menu = QMenu(self.speed_button)
        self._speed_group = QActionGroup(self)
        self._speed_actions: dict[float, QAction] = {}
        for rate in PLAYBACK_RATES:
            action = self._speed_menu.addAction(rate_label(rate))
            action.setCheckable(True)
            action.setChecked(rate == 1.0)
            action.triggered.connect(lambda _=False, r=rate: self.rate_selected.emit(r))
            self._speed_group.addAction(action)
            self._speed_actions[rate] = action
        self.speed_button.setMenu(self._speed_menu)
        self.tracks_button = QToolButton()
        self.tracks_button.setObjectName("tracksButton")
        self.tracks_button.setIcon(icon(self, "subtitles"))
        self.tracks_button.setIconSize(QSize(16, 16))
        self.tracks_button.setFixedSize(32, 32)
        self.tracks_button.setAccessibleName("Audio and subtitles")
        self.tracks_button.setToolTip("Audio and subtitles (V cycles subtitles, B cycles audio)")
        self.tracks_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tracks_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tracks_menu = QMenu(self.tracks_button)
        self.tracks_menu.aboutToShow.connect(lambda: self.tracks_menu_opening.emit(self.tracks_menu))
        self.tracks_button.setMenu(self.tracks_menu)
        self.mute_button = self._button("volume", "Mute", "Mute (M)", self.mute_clicked)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(VOLUME_MIN, 100)
        self.volume.setFixedWidth(96)
        self.volume.setAccessibleName("Volume")
        self.volume.setToolTip("Volume (↑/↓)")
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume.valueChanged.connect(self.volume_changed)
        self.volume_label = self._label(str(VOLUME_MIN), "time", "Volume level")
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume_label.setMinimumWidth(self.volume_label.fontMetrics().horizontalAdvance("200"))
        self.fullscreen_button = self._button(
            "fullscreen", "Fullscreen", "Fullscreen (F)", self.fullscreen_clicked
        )

        for widget in (
            self.play_button,
            self.previous_button,
            self.back_button,
            self.forward_button,
            self.next_button,
            self.stop_button,
        ):
            row.addWidget(widget)
        row.addSpacing(theme.S)
        row.addWidget(self.title_label, stretch=1)
        for trailing in (
            self.favourite_button,
            self.shuffle_button,
            self.repeat_button,
            self.queue_button,
            self.tracks_button,
            self.speed_button,
            self.mute_button,
            self.volume,
            self.volume_label,
            self.fullscreen_button,
        ):
            row.addWidget(trailing)
        outer.addLayout(row)
        self._title = ""
        self.set_list_available(False)

    # ------------------------------------------------------------ build
    def _label(self, text: str, name: str, accessible: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setAccessibleName(accessible)
        return label

    def _button(self, glyph: str, name: str, tip: str, signal: SignalInstance, size: int = 32) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon(self, glyph))
        self._plain_icons.append((button, glyph))
        button.setIconSize(QSize(size // 2, size // 2))
        button.setFixedSize(size, size)
        button.setAccessibleName(name)
        button.setToolTip(tip)
        # Playback shortcuts own Space/arrows; buttons are mouse targets (menus offer keyboard access).
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(signal)
        return button

    # ------------------------------------------------------------ state
    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.play_button.setIcon(icon(self, "pause" if playing else "play", theme.ON_ACCENT))
        self.play_button.setAccessibleName("Pause" if playing else "Play")

    def set_enabled_controls(self, *, play: bool, stop: bool, seek: bool) -> None:
        self.play_button.setEnabled(play)
        self.stop_button.setEnabled(stop)
        for widget in (self.seek, self.back_button, self.forward_button):
            widget.setEnabled(seek)
        self.speed_button.setEnabled(play)
        self.tracks_button.setEnabled(play)

    def set_list_available(self, available: bool) -> None:
        """Previous, next, shuffle and queue only mean something with a list to move through."""
        self._has_list = available
        self.apply_width(self.width())

    def set_list_controls(self, *, previous: bool, next_item: bool) -> None:
        self.previous_button.setEnabled(previous)
        self.next_button.setEnabled(next_item)

    def refresh_theme(self) -> None:
        """Lit buttons hold their colour in an icon, so they're drawn again."""
        for button, glyph in self._plain_icons:
            button.setIcon(icon(self, glyph))
        self.tracks_button.setIcon(icon(self, "subtitles"))
        self.set_playing(self._playing)
        self.set_muted(self._muted)
        self.set_fullscreen(self._fullscreen)
        self.set_favourite(self._can_favourite, self._favourite)
        self.set_repeat(self._repeat)
        self.set_shuffle(self._shuffle_on)

    def set_favourite(self, available: bool, favourite: bool) -> None:
        self._can_favourite = available
        self._favourite = favourite
        self.favourite_button.setIcon(
            icon(self, "heart_filled" if favourite else "heart", theme.RED if favourite else theme.TEXT)
        )
        name = "Remove from favourites" if favourite else "Add to favourites"
        self.favourite_button.setAccessibleName(name)
        self.favourite_button.setToolTip(f"{name} (U)")
        self.apply_width(self.width())

    def set_shuffle(self, on: bool) -> None:
        self._shuffle_on = on
        self.shuffle_button.setIcon(icon(self, "shuffle", theme.CYAN if on else theme.TEXT))
        self.shuffle_button.setAccessibleName("Shuffle is on" if on else "Shuffle is off")

    def set_repeat(self, mode: RepeatMode) -> None:
        self._repeat = mode
        glyph = "repeat_one" if mode is RepeatMode.ONE else "repeat"
        self.repeat_button.setIcon(icon(self, glyph, theme.TEXT if mode is RepeatMode.OFF else theme.CYAN))
        self.repeat_button.setAccessibleName(REPEAT_NAMES[mode])
        self.repeat_button.setToolTip(f"{REPEAT_NAMES[mode]} (R)")

    def set_position(self, position_ms: int, duration_ms: int | None) -> None:
        if duration_ms is not None and self.seek.maximum() != duration_ms:
            self.seek.setRange(0, duration_ms)
            self.duration_label.setText(format_time(duration_ms))
        if not self.seek.user_dragging:
            self.seek.setValue(position_ms)
        self.time_label.setText(format_time(self.seek.value() if self.seek.user_dragging else position_ms))

    def reset_position(self) -> None:
        self.seek.setRange(0, 0)
        self.time_label.setText(format_time(0))
        self.duration_label.setText(format_time(None))

    def set_title(self, title: str) -> None:
        self._title = title
        self._elide_title()

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self.mute_button.setIcon(icon(self, "mute" if muted else "volume"))
        self.mute_button.setAccessibleName("Unmute" if muted else "Mute")

    def set_volume(self, level: int) -> None:
        self.volume.blockSignals(True)
        self.volume.setValue(level)
        self.volume.blockSignals(False)
        self.volume_label.setText(str(self.volume.value()))
        self._mark_boost(level)

    def set_volume_maximum(self, maximum: int) -> None:
        """100, or up to 200 when volume boost is allowed (M7)."""
        self.volume.setMaximum(maximum)
        tip = "Volume (↑/↓)" if maximum <= 100 else "Volume (↑/↓) · above 100 % may distort loud passages"
        self.volume.setToolTip(tip)
        self._mark_boost(self.volume.value())

    def _mark_boost(self, level: int) -> None:
        boosted = level > 100
        if self.volume.property("boost") != boosted:
            self.volume.setProperty("boost", boosted)
            self.volume.style().unpolish(self.volume)
            self.volume.style().polish(self.volume)

    def set_rate(self, rate: float) -> None:
        self.speed_button.setText(rate_label(rate))
        if rate in self._speed_actions:
            self._speed_actions[rate].setChecked(True)

    def set_fullscreen(self, fullscreen: bool) -> None:
        self._fullscreen = fullscreen
        self.fullscreen_button.setIcon(icon(self, "exit_fullscreen" if fullscreen else "fullscreen"))
        self.fullscreen_button.setToolTip("Exit fullscreen (Esc)" if fullscreen else "Fullscreen (F)")
        self.fullscreen_button.setAccessibleName("Exit fullscreen" if fullscreen else "Fullscreen")

    # -------------------------------------------------------- responsive
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.apply_width(event.size().width())

    def apply_width(self, width: int) -> None:
        compact = width < COMPACT_WIDTH
        narrow = width < NARROW_WIDTH
        self.stop_button.setVisible(not compact)
        self.volume.setVisible(not compact)
        self.volume_label.setVisible(not compact)
        self.speed_button.setVisible(not narrow)
        self.back_button.setVisible(not narrow)
        self.forward_button.setVisible(not narrow)
        self.repeat_button.setVisible(not narrow)
        self.favourite_button.setVisible(self._can_favourite)
        self.previous_button.setVisible(self._has_list)
        self.next_button.setVisible(self._has_list)
        self.shuffle_button.setVisible(self._has_list and not compact)
        self.queue_button.setVisible(self._has_list and not narrow)
        self._elide_title()

    def _elide_title(self) -> None:
        metrics = self.title_label.fontMetrics()
        available = max(40, self.title_label.width())
        self.title_label.setText(metrics.elidedText(self._title, Qt.TextElideMode.ElideMiddle, available))
        self.title_label.setToolTip(self._title)
