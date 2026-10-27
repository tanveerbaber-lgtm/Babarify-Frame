"""M1 shell window: branding, an honest empty state, and engine availability."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from babarify_frame import BRAND, PRODUCT_NAME, TAGLINE, __version__
from babarify_frame.playback.factory import EngineFactory, EngineProbe
from babarify_frame.ui import theme
from babarify_frame.ui.bridge import UiBridge

CANDIDATE_ENGINES = ("libvlc", "mpv")


def _named[W: QWidget](widget: W, name: str) -> W:
    """Set the Qt object name used by the stylesheet (PySide's stubs reject it as a constructor keyword)."""
    widget.setObjectName(name)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, factory: EngineFactory, icon: QIcon) -> None:
        super().__init__()
        self._factory = factory
        self._bridge = UiBridge(self)
        self._bridge.delivered.connect(self._on_probe_result)
        self._engine_labels: dict[str, QLabel] = {}
        self._probe_thread: threading.Thread | None = None
        self.probe_results: dict[str, EngineProbe] = {}

        self.setWindowTitle(PRODUCT_NAME)
        self.setWindowIcon(icon)
        self.setMinimumSize(720, 480)
        self.resize(1100, 700)

        root = _named(QWidget(), "root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(18)
        layout.addLayout(self._build_header(icon))
        layout.addWidget(self._build_video_area(), stretch=1)
        layout.addWidget(self._build_engine_panel())
        self.setCentralWidget(root)
        self._build_menu()
        self.statusBar().showMessage(f"Version {__version__} · Local-only · No telemetry")

    # ----------------------------------------------------------- layout
    def _build_header(self, icon: QIcon) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icon.pixmap(48, 48))
        logo.setAccessibleName(f"{PRODUCT_NAME} logo")
        header.addWidget(logo)

        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(_named(QLabel(BRAND.upper()), "brand"))
        text.addWidget(_named(QLabel(PRODUCT_NAME), "productName"))
        header.addLayout(text)
        header.addStretch(1)
        header.addWidget(_named(QLabel(TAGLINE), "tagline"), alignment=Qt.AlignmentFlag.AlignBottom)
        return header

    def _build_video_area(self) -> QFrame:
        area = _named(QFrame(), "videoArea")
        area.setAccessibleName("Video area")
        box = QVBoxLayout(area)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = _named(QLabel("No media open"), "emptyTitle")
        body = _named(
            QLabel(
                "Playback arrives in Milestone 2, once a playback engine has been chosen.\n"
                "This build checks which engines can load on this PC."
            ),
            "emptyBody",
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        box.addWidget(body, alignment=Qt.AlignmentFlag.AlignCenter)
        return area

    def _build_engine_panel(self) -> QFrame:
        panel = _named(QFrame(), "enginePanel")
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 12, 16, 12)
        box.addWidget(_named(QLabel("PLAYBACK ENGINE CANDIDATES"), "panelTitle"))
        for name in CANDIDATE_ENGINES:
            label = QLabel(f"{self._factory.descriptor(name).display_name}: checking…")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._engine_labels[name] = label
            box.addWidget(label)
        return panel

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        open_action = QAction("&Open file…", self, enabled=False)
        open_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        open_action.setToolTip("Available in Milestone 2")
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction(f"&About {PRODUCT_NAME}", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    # ---------------------------------------------------- engine probes
    def start_engine_probes(self, names: Sequence[str] = CANDIDATE_ENGINES) -> None:
        """Probe engines on a worker thread so a slow DLL load never blocks the UI."""

        def work() -> None:
            for name in names:
                self._bridge.post(self._factory.probe(name))

        self._probe_thread = threading.Thread(target=work, name="engine-probe", daemon=True)
        self._probe_thread.start()

    def _on_probe_result(self, payload: object) -> None:
        if not isinstance(payload, EngineProbe):
            return
        self.probe_results[payload.name] = payload
        label = self._engine_labels.get(payload.name)
        if label is None:
            return
        display = self._factory.descriptor(payload.name).display_name
        if payload.available:
            label.setText(f"<span style='color:{theme.GREEN}'>●</span> {display}: loaded {payload.version}")
        else:
            label.setText(
                f"<span style='color:{theme.AMBER}'>●</span> {display}: unavailable — {payload.detail}"
            )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {PRODUCT_NAME}",
            f"<b>{PRODUCT_NAME}</b> {__version__}<br>{TAGLINE}<br><br>"
            "Free, no ads, no account, no telemetry.<br>"
            "Milestone 1 build: playback engines are being evaluated.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._probe_thread is not None:
            self._probe_thread.join(timeout=5)
        super().closeEvent(event)
