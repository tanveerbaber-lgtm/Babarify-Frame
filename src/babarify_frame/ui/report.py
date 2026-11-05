"""Help → Report a problem (M11): prepares a report for the user to copy. Nothing is sent.

The text contains the app and Windows versions, the engine and decoder, the codecs of the open
media and the last error. The file name and recent log lines are left out unless the user ticks
them; the user's profile folder is replaced by %USERPROFILE% everywhere. "Open the issue page"
only opens the project's issue form in the browser; the user pastes the text there.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame import __version__, app_log
from babarify_frame.core.models import MediaInfo

ISSUES_URL = "https://github.com/tanveerbaber-lgtm/Babarify-Frame/issues/new/choose"
LOG_LINES = 40


def redact(text: str) -> str:
    home = str(Path.home())
    for variant in {home, home.replace("\\", "/"), home.lower()}:
        text = text.replace(variant, "%USERPROFILE%")
    return text


def report_text(
    diagnostics: dict[str, str],
    info: MediaInfo | None,
    media_name: str,
    last_error: str,
    include_name: bool,
    include_log: bool,
    log_lines: list[str],
) -> str:
    lines = [
        f"Babarify Media Player {__version__}",
        f"Windows: {platform.platform()} ({platform.machine()})",
    ]
    lines += [f"{key}: {value}" for key, value in diagnostics.items()]
    if info is not None:
        video = f"{info.video_codec} {info.width}x{info.height}" if info.video_codec else "none"
        lines += [f"Media video: {video}", f"Media audio: {info.audio_codec or 'none'}"]
        if include_name and media_name:
            lines.append(f"Media name: {media_name}")
    else:
        lines.append("Media: nothing open")
    lines.append(f"Last error: {last_error or 'none'}")
    if include_log:
        lines += ["", f"Recent log ({len(log_lines)} lines):", *log_lines]
    return redact("\n".join(lines)) + "\n"


def recent_log(limit: int = LOG_LINES) -> list[str]:
    path = app_log.log_dir() / "app.log"
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []


class ReportDialog(QDialog):
    def __init__(
        self,
        gather: Callable[[], tuple[dict[str, str], MediaInfo | None, str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Report a problem")
        self.resize(620, 560)
        self._gather = gather
        box = QVBoxLayout(self)
        intro = QLabel(
            "This text helps us understand the problem. Nothing is sent from this window: copy it and "
            "paste it into the issue form, together with what you did and what happened."
        )
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.include_name = QCheckBox("Include the name of the open file")
        self.include_log = QCheckBox(f"Include the last {LOG_LINES} log lines (they can contain file names)")
        for check in (self.include_name, self.include_log):
            check.toggled.connect(self.refresh)
            box.addWidget(check)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setAccessibleName("Report text")
        box.addWidget(self.text, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button = QPushButton("Copy")
        self.issue_button = QPushButton("Open the issue page")
        self.logs_button = QPushButton("Open log folder")
        for button in (self.copy_button, self.issue_button, self.logs_button):
            buttons.addButton(button, QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.clicked.connect(self._copy)
        self.issue_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ISSUES_URL)))
        self.logs_button.clicked.connect(self._open_logs)
        buttons.rejected.connect(self.close)
        box.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        diagnostics, info, name, error = self._gather()
        log = recent_log() if self.include_log.isChecked() else []
        self.text.setPlainText(
            report_text(
                diagnostics,
                info,
                name,
                error,
                self.include_name.isChecked(),
                self.include_log.isChecked(),
                log,
            )
        )
        self.copy_button.setText("Copy")

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())
        self.copy_button.setText("Copied")

    def _open_logs(self) -> None:
        folder = app_log.log_dir()
        if folder.is_dir():
            os.startfile(folder)
