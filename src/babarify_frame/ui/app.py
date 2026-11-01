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

from babarify_frame import BRAND, PRODUCT_NAME, __version__, app_log
from babarify_frame.library.database import LibraryDatabase, default_database_path
from babarify_frame.library.service import LibraryService, default_thumbnail_dir
from babarify_frame.playback.factory import EngineFactory, default_factory
from babarify_frame.playback.media_probe import MediaProbe
from babarify_frame.playback.preview import FramePreview
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


def _libvlc_probe() -> MediaProbe:
    from babarify_frame.playback.adapters.libvlc_probe import LibVlcProbe

    return LibVlcProbe()


def libvlc_preview() -> FramePreview:
    from babarify_frame.playback.adapters.libvlc_preview import LibVlcPreview

    return LibVlcPreview()


def create_library() -> LibraryService:
    """The local library database plus a background worker; thumbnails use libVLC when present."""
    path = default_database_path()
    return LibraryService(LibraryDatabase(path), _libvlc_probe, default_thumbnail_dir(path))


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
    if not logging.getLogger().handlers:  # tests configure logging themselves
        app_log.setup(__version__)
    _set_windows_app_id()

    app = QApplication.instance() or QApplication(sys.argv[:1])
    assert isinstance(app, QApplication)
    app.setApplicationName(PRODUCT_NAME)
    app.setOrganizationName(BRAND)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLESHEET)
    icon = load_icon()
    app.setWindowIcon(icon)

    preview = libvlc_preview if args.engine == "libvlc" else None  # previews need libVLC (M8)
    window = MainWindow(
        factory, icon, engine_name=args.engine, library=create_library(), preview_factory=preview
    )
    window.show()
    window.start_engine()
    if args.file:
        window.open_path(args.file)

    if args.smoke_test is not None:

        def finish_smoke_test() -> None:
            status = window.controller.status() if window.player.engine_is_ready else None
            logging.getLogger(__name__).info(  # recorded for the release check (M10)
                "smoke test: state=%s position_ms=%s",
                status.state.value if status is not None else "engine not ready",
                status.position_ms if status is not None else 0,
            )
            window.close()

        QTimer.singleShot(args.smoke_test, finish_smoke_test)

    code = app.exec()
    logging.getLogger(__name__).info("exited cleanly with code %s", code)
    return code
