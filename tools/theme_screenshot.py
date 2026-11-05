"""Capture the real app in every colour theme, and the equalizer's dials.

Uses throw-away settings and a throw-away library, so the user's real ones are never touched.
Usage:  python tools/theme_screenshot.py <output folder> <folder of songs>
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

_PROFILE = tempfile.mkdtemp(prefix="babarify-theme-")
os.environ["BABARIFY_CONFIG_DIR"] = _PROFILE

from babarify_frame.configuration.preferences import PreferencesStore  # noqa: E402
from babarify_frame.core.models import PlaybackState as S  # noqa: E402
from babarify_frame.core.themes import THEMES  # noqa: E402
from babarify_frame.library.database import LibraryDatabase  # noqa: E402
from babarify_frame.library.service import LibraryService  # noqa: E402
from babarify_frame.playback.adapters.libvlc_probe import LibVlcProbe  # noqa: E402
from babarify_frame.playback.factory import default_factory  # noqa: E402
from babarify_frame.ui import theme  # noqa: E402
from babarify_frame.ui.app import load_icon  # noqa: E402
from babarify_frame.ui.main_window import MainWindow  # noqa: E402


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.STYLESHEET)
    service = LibraryService(LibraryDatabase(None), LibVlcProbe, thumbnail_dir=Path(_PROFILE) / "thumbnails")
    store = PreferencesStore(Path(_PROFILE) / "settings.json")
    window = MainWindow(default_factory(), load_icon(), engine_name="libvlc", store=store, library=service)
    window.resize(1280, 800)
    window.show()
    window.start_engine()
    pump(app, 2)
    window.show_page(window.library)
    window.library.add_folder(sys.argv[2])
    end = time.perf_counter() + 60
    while (service.busy or service.db.counts()[2]) and time.perf_counter() < end:
        pump(app, 0.2)
    window.library.tabs.setCurrentIndex(1)
    pump(app, 0.5)
    combo = window.settings.colour_theme
    for key in THEMES:
        combo.setCurrentIndex(combo.findData(key))
        pump(app, 0.5)
        window.grab().save(str(out / f"theme_{key}.png"))
    combo.setCurrentIndex(combo.findData("light"))
    pump(app, 0.5)
    tabs = window.library.tabs
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        pump(app, 0.4)
        window.grab().save(str(out / f"light_library_{tabs.tabText(index).lower()}.png"))
    window.show_page(window.home)
    pump(app, 0.5)
    window.grab().save(str(out / "light_home.png"))
    window.show_page(window.settings)
    pump(app, 0.5)
    window.grab().save(str(out / "light_settings.png"))
    window.player.play_queue([song.path for song in service.db.songs()])
    window.show_page(window.player)
    pump(app, 3)
    window.grab().save(str(out / "light_playing_picture.png"))
    plain = [song.path for song in service.db.songs() if not song.thumbnail]
    if plain:
        window.player.play_queue(plain)
        pump(app, 3)
        window.grab().save(str(out / "light_playing_animation.png"))
    window.show_enhancements()
    light_dialog = window._enhancements
    assert light_dialog is not None
    light_dialog.tabs.setCurrentIndex(2)
    pump(app, 0.4)
    light_dialog.grab().save(str(out / "light_equalizer.png"))
    light_dialog.close()
    window.player.stop()
    pump(app, 0.5)
    window.grab().save(str(out / "light_stopped.png"))
    combo.setCurrentIndex(combo.findData("ocean"))
    window.show_page(window.settings)
    pump(app, 0.5)
    window.grab().save(str(out / "settings.png"))

    window.player.play_queue([song.path for song in service.db.songs()])
    window.show_page(window.player)
    end = time.perf_counter() + 20
    while window.player.state is not S.PLAYING and time.perf_counter() < end:
        pump(app, 0.1)
    window.show_enhancements()
    dialog = window._enhancements
    assert dialog is not None
    dialog.tabs.setCurrentIndex(2)
    dialog.eq_enabled.setChecked(True)
    dialog.bass.setValue(60)
    dialog.preamp.setValue(-4)
    pump(app, 0.5)
    print("bands after the bass dial:", dialog.equalizer().bands_db)
    print("still playing:", window.player.state is S.PLAYING)
    dialog.grab().save(str(out / "equalizer.png"))
    dialog.reset_eq_button.click()
    dialog.close()
    window.player.stop()
    pump(app, 0.5)
    window.close()
    pump(app, 1)


if __name__ == "__main__":
    main()
