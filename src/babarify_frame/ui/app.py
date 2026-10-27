"""Application entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from babarify_frame import BRAND, PRODUCT_NAME, __version__
from babarify_frame.playback.factory import EngineFactory, default_factory
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.theme import STYLESHEET

ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"
APP_USER_MODEL_ID = "Babarify.Frame"
DEFAULT_ENGINE = "libvlc"  # ADR-0001 (accepted, provisional)


def load_icon() -> QIcon:
    icon = QIcon()
    for px in (16, 32, 64, 256):
        icon.addFile(str(ICON_DIR / f"babarify-frame-{px}.png"))
    return icon


def _set_windows_app_id() -> None:
    """Give the process its own taskbar identity so Windows shows our icon, not python.exe's."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def parse_args(argv: Sequence[str] | None, engines: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="babarify-frame", description=f"{PRODUCT_NAME} {__version__}")
    parser.add_argument("file", nargs="?", help="media file to open")
    parser.add_argument(
        "--engine",
        choices=list(engines),
        default=DEFAULT_ENGINE,
        help=f"playback engine (default: {DEFAULT_ENGINE})",
    )
    parser.add_argument(
        "--smoke-test",
        nargs="?",
        type=int,
        const=1500,
        metavar="MS",
        help="open the window (and FILE, if given), then exit after MS milliseconds",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, factory: EngineFactory | None = None) -> int:
    factory = factory or default_factory()
    args = parse_args(argv, factory.names())
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _set_windows_app_id()

    app = QApplication.instance() or QApplication(sys.argv[:1])
    assert isinstance(app, QApplication)
    app.setApplicationName(PRODUCT_NAME)
    app.setOrganizationName(BRAND)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLESHEET)
    icon = load_icon()
    app.setWindowIcon(icon)

    window = MainWindow(factory, icon, engine_name=args.engine)
    window.show()
    window.start_engine()
    if args.file:
        window.open_path(args.file)

    if args.smoke_test is not None:
        QTimer.singleShot(args.smoke_test, window.close)

    code = app.exec()
    logging.getLogger(__name__).info("exited cleanly with code %s", code)
    return code
