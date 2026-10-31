"""Capture M6 evidence screenshots: Library grid, Home with Continue watching, playlists, Settings.

Uses a throw-away settings and library folder, so the user's real preferences, library and
history are never touched. Reuses the ownership check from player_screenshot.py (R16): a
screenshot is saved only if every sampled point of the window belongs to this window.
Usage:  python tools/library_screenshot.py docs/milestones/M6/evidence
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.ui.main_window import MainWindow
from player_screenshot import MEDIA, grab, pump, wait


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["BABARIFY_CONFIG_DIR"] = tempfile.mkdtemp(prefix="babarify-library-shots-")
    from babarify_frame.playback.factory import default_factory
    from babarify_frame.ui.app import create_library, load_icon
    from babarify_frame.ui.theme import STYLESHEET

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    library = create_library()
    store = PreferencesStore(Path(os.environ["BABARIFY_CONFIG_DIR"]) / "settings.json")
    window = MainWindow(default_factory(), load_icon(), store=store, library=library)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.resize(1180, 740)
    window.show()
    window.start_engine()
    wait(app, window, S.READY)

    window.show_page(window.library)
    grab(app, window, out / "library_empty.png")

    started = time.perf_counter()
    window.library.add_folder(str(MEDIA))
    while library.busy and time.perf_counter() - started < 300:
        pump(app, 0.2)
    pump(app, 1.0)
    total, missing, pending = library.db.counts()
    print(
        f"library: {total} files, {missing} missing, {pending} pending, {time.perf_counter() - started:.1f} s"
    )
    grab(app, window, out / "library_grid.png")

    window.library.search.setText("h264")
    pump(app, 0.6)
    grab(app, window, out / "library_search.png")
    window.library.search.clear()
    pump(app, 0.4)

    for name, fraction in (("e_long_1h_240p.mkv", 0.35), ("hevc_2160p30_aac.mkv", 0.5)):
        window.open_path(str(MEDIA / name))
        wait(app, window, S.PLAYING)
        while not window.controller.status().duration_ms:  # reported shortly after playback starts
            pump(app, 0.05)
        duration = window.controller.status().duration_ms or 0
        window.player.seek_to(int(duration * fraction))
        pump(app, 1.5)
    window.open_path(str(MEDIA / "c_h264_aac_720p.mkv"))
    wait(app, window, S.PLAYING)
    pump(app, 1.0)
    window.player.stop()
    window.show_page(window.home)
    pump(app, 0.5)
    grab(app, window, out / "home_continue_watching.png")

    db = library.db
    pid = db.create_playlist("Weekend").id
    db.add_to_playlist(
        pid, [str(MEDIA / n) for n in ("c_vp8_vorbis_720p.webm", "gone.mp4", "c_audio_flac.flac")]
    )
    window.show_page(window.library)
    window.library.tabs.setCurrentIndex(1)
    window.library.playlists.refresh(select=pid)
    pump(app, 0.4)
    grab(app, window, out / "library_playlists.png")

    window.show_page(window.settings)
    scroll = window.settings.layout().itemAt(0).widget()
    if hasattr(scroll, "verticalScrollBar"):
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    pump(app, 0.4)
    grab(app, window, out / "settings_privacy.png")

    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
