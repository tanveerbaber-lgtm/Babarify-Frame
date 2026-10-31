"""Playback info panel (M4): what the engine is actually doing, in plain words, plus its recent log.

Everything shown comes from the engine through the playback contract (media info, status,
capabilities, diagnostics, frame counters, log). Nothing is inferred or promised: the decoder
line says "hardware" only when the engine confirmed it. The text stays on this PC unless the
user copies it.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QGuiApplication, QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.core.models import PlaybackState
from babarify_frame.playback.controller import PlaybackController
from babarify_frame.ui import theme
from babarify_frame.ui.widgets import format_time

REFRESH_MS = 500
LOG_LINES = 40
FIELDS = (
    "Engine",
    "State",
    "File",
    "Video",
    "Frame rate",
    "Audio",
    "Decoder",
    "Hardware decoding setting",
    "Video output",
    "Frames displayed / dropped",
    "Position",
    "Last error",
)


def collect(controller: PlaybackController, last_error: str) -> dict[str, str]:
    """Snapshot of the current playback as label -> text. Safe to call with no engine."""
    if controller.engine_name is None:
        return {"Engine": "not running"}
    engine = controller.engine
    status = controller.status()
    info = controller.media_info()
    caps = controller.capabilities()
    diag = engine.diagnostics()
    stats = engine.playback_stats()
    rows = {
        "Engine": diag.get("engine", f"{caps.engine_name} {caps.engine_version}"),
        "State": status.state.value,
        "File": status.uri or "—",
        "Video": "—",
        "Frame rate": "—",
        "Audio": "—",
        "Decoder": diag.get("decoder", "unknown"),
        "Hardware decoding setting": {"requested": "Automatic", "disabled": "Off"}.get(
            caps.hardware_decoding, caps.hardware_decoding
        ),
        "Video output": diag.get("video_output", "unknown"),
        "Frames displayed / dropped": "—",
        "Position": f"{format_time(status.position_ms)} / {format_time(status.duration_ms)}",
        "Last error": last_error or "none",
    }
    if info is not None:
        if info.video_codec:
            rows["Video"] = f"{info.video_codec}  {info.width or '?'}×{info.height or '?'}"  # noqa: RUF001
            rows["Frame rate"] = f"{info.frame_rate:.3f} fps" if info.frame_rate else "unknown"
        else:
            rows["Video"] = "none (audio only)"
        if info.audio_codec:
            audio_tracks = sum(1 for t in info.tracks if t.kind.value == "audio")
            rows["Audio"] = f"{info.audio_codec}  ({audio_tracks} track{'s' if audio_tracks != 1 else ''})"
    if "displayed" in stats or "dropped" in stats:
        shown = stats.get("displayed")
        rows["Frames displayed / dropped"] = (
            f"{shown if shown is not None else '?'} / {stats.get('dropped', 0)}"
        )
    if status.state is PlaybackState.UNINITIALIZED:
        rows["State"] = "starting"
    return rows


def as_text(rows: dict[str, str], log: list[str]) -> str:
    width = max(len(k) for k in rows)
    lines = [f"{k.ljust(width)}  {v}" for k, v in rows.items()]
    return "\n".join([*lines, "", "Recent engine log:", *log])


class PlaybackInfoDialog(QDialog):
    def __init__(
        self, controller: PlaybackController, last_error: Callable[[], str], parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Playback info")
        self.setMinimumSize(620, 520)
        self._controller = controller
        self._last_error = last_error
        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.L, theme.L, theme.L, theme.L)
        layout.setSpacing(theme.M)
        form = QFormLayout()
        form.setHorizontalSpacing(theme.XL)
        self._values: dict[str, QLabel] = {}
        for name in FIELDS:
            value = QLabel("—")
            value.setObjectName("muted")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._values[name] = value
            form.addRow(name, value)
        layout.addLayout(form)
        layout.addWidget(QLabel("Recent engine log"))
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._log.setAccessibleName("Recent engine log")
        layout.addWidget(self._log, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button = QPushButton("Copy to clipboard")
        self.copy_button.setAccessibleName("Copy playback info to clipboard")
        buttons.addButton(self.copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event: QShowEvent) -> None:
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def snapshot(self) -> tuple[dict[str, str], list[str]]:
        rows = collect(self._controller, self._last_error())
        log = self._controller.engine.recent_log()[-LOG_LINES:] if self._controller.engine_name else []
        return rows, log

    def refresh(self) -> None:
        rows, log = self.snapshot()
        for name, label in self._values.items():
            label.setText(rows.get(name, "—"))
        text = "\n".join(log)
        if text != self._log.toPlainText():
            self._log.setPlainText(text)
            self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def copy_to_clipboard(self) -> None:
        rows, log = self.snapshot()
        QGuiApplication.clipboard().setText(as_text(rows, log))
        self.copy_button.setText("Copied")
        # Context object: Qt drops the timer if the dialog (and button) is deleted first (R22).
        button = self.copy_button
        QTimer.singleShot(1500, button, lambda: button.setText("Copy to clipboard"))
