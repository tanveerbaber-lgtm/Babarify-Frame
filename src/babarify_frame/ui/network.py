"""Open network stream dialog (M8).

The address is checked while typing with the same rules the engine applies
(``validate_stream_url``), so the reason a stream is refused is shown before anything is
fetched. Recent streams come from the local history (when history is on).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.core.errors import PlaybackError
from babarify_frame.core.network import stream_display_name, validate_stream_url
from babarify_frame.ui.widgets import plain_text

HELP = (
    "Supported: http:// and https:// (files, HLS .m3u8, M3U/PLS playlists, internet radio) and "
    "rtsp://. Web streams are fetched by Babarify itself: redirects are followed only to other web "
    "addresses, and playlist entries that point at local files or other programs are skipped."
)


class NetworkStreamDialog(QDialog):
    def __init__(self, schemes: frozenset[str], recent: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Open network stream")
        self.setMinimumWidth(560)
        self._schemes = schemes
        box = QVBoxLayout(self)
        box.addWidget(QLabel("Stream address"))
        self.address = QLineEdit()
        self.address.setPlaceholderText("https://example.com/live/stream.m3u8")
        self.address.setAccessibleName("Stream address")
        self.address.setMaxLength(4096)  # longer input is refused with a reason, not cut silently
        self.address.textChanged.connect(self._check)
        box.addWidget(self.address)
        self.reason = QLabel()
        self.reason.setObjectName("muted")
        self.reason.setWordWrap(True)
        plain_text(self.reason)
        box.addWidget(self.reason)
        self.recent = QListWidget()
        self.recent.setAccessibleName("Recent streams")
        for url in recent:
            item = QListWidgetItem(stream_display_name(url))
            item.setData(Qt.ItemDataRole.UserRole, url)
            item.setToolTip(stream_display_name(url))
            self.recent.addItem(item)
        self.recent.itemClicked.connect(
            lambda item: self.address.setText(item.data(Qt.ItemDataRole.UserRole))
        )
        self.recent.itemDoubleClicked.connect(lambda _item: self.accept() if self.url else None)
        self.recent.setVisible(bool(recent))
        self.recent.setMaximumHeight(140)
        if recent:
            box.addWidget(QLabel("Recent streams"))
        box.addWidget(self.recent)
        note = QLabel(HELP)
        note.setObjectName("muted")
        note.setWordWrap(True)
        box.addWidget(note)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)
        self.url: str | None = None
        if not schemes:
            self.address.setEnabled(False)
        self._check("")

    def _check(self, text: str) -> None:
        open_button = self.buttons.button(QDialogButtonBox.StandardButton.Open)
        self.url = None
        if not self._schemes:
            self.reason.setText("The current playback engine cannot play network streams.")
        elif not text.strip():
            self.reason.setText("")
        else:
            try:
                self.url = validate_stream_url(text, self._schemes)
                self.reason.setText(f"Opens {stream_display_name(self.url)}")
            except PlaybackError as exc:
                self.reason.setText(exc.detail[:1].upper() + exc.detail[1:] + ".")
        open_button.setEnabled(self.url is not None)
