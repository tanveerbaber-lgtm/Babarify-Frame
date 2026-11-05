"""Capture the Library's music tabs from a real folder of songs, and time them on a large library.

Uses throw-away settings and a throw-away library, so the user's real ones are never touched.
Usage:  python tools/music_screenshot.py <output folder> <folder of songs>
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

_PROFILE = tempfile.mkdtemp(prefix="babarify-music-")
os.environ["BABARIFY_CONFIG_DIR"] = _PROFILE

from babarify_frame.configuration.preferences import PreferencesStore  # noqa: E402
from babarify_frame.library.database import LibraryDatabase, ProbeRecord, ScanRecord  # noqa: E402
from babarify_frame.library.music import GroupKind, group_songs  # noqa: E402
from babarify_frame.library.service import LibraryService  # noqa: E402
from babarify_frame.playback.adapters.libvlc_probe import LibVlcProbe  # noqa: E402
from babarify_frame.playback.factory import default_factory  # noqa: E402
from babarify_frame.ui.app import load_icon  # noqa: E402
from babarify_frame.ui.main_window import MainWindow  # noqa: E402
from babarify_frame.ui.theme import STYLESHEET  # noqa: E402

LARGE = 20_000


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def time_large_library() -> None:
    db = LibraryDatabase(None)
    with tempfile.TemporaryDirectory() as folder_path:
        folder = db.add_folder(folder_path).id
        db.upsert_media(
            [ScanRecord(f"C:/m/{i % 400}/{i}.mp3", folder, 1, 1.0, None) for i in range(LARGE)], time.time()
        )
        for entry_id, _path in db.media_to_probe(LARGE):
            db.set_probe_result(
                entry_id,
                ProbeRecord(
                    1000,
                    None,
                    None,
                    None,
                    "mp3",
                    None,
                    f"Song {entry_id}",
                    f"Artist {entry_id % 300}",
                    f"Album {entry_id % 900}",
                ),
            )
        started = time.perf_counter()
        songs = db.songs()
        read = time.perf_counter() - started
        started = time.perf_counter()
        albums = group_songs(songs, GroupKind.ALBUM)
        grouped = time.perf_counter() - started
        print(f"{len(songs)} songs read in {read * 1000:.0f} ms")
        print(f"{len(albums)} albums in {grouped * 1000:.0f} ms")
    db.close()


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
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
    pump(app, 0.5)
    songs = service.db.songs()
    print(f"found {len(songs)} songs; pictures on {sum(1 for s in songs if s.thumbnail)}")
    for song in songs:
        print(f"  {song.display_title!r} / {song.artist!r} / {song.album!r} / {song.duration_ms}")
    tabs = window.library.tabs
    for index in range(tabs.count()):
        name = tabs.tabText(index)
        tabs.setCurrentIndex(index)
        pump(app, 0.5)
        if name == "Playlists":
            db = service.db
            for song in songs[:2]:
                db.set_favourite(song.path, song.display_title, True)
            window.library.playlists.automatic.setCurrentRow(3)
            pump(app, 0.3)
        window.grab().save(str(out / f"tab_{name.lower()}.png"))
    window.library.tabs.setCurrentIndex(2)
    pump(app, 0.3)
    panel = window.library.albums_panel
    panel.open_group(panel.groups.groups[0])
    pump(app, 0.3)
    window.grab().save(str(out / "album_open.png"))
    panel.play_all()
    pump(app, 2.5)
    window.grab().save(str(out / "playing.png"))
    window.player.stop()
    pump(app, 0.5)
    window.close()
    pump(app, 1)
    time_large_library()


if __name__ == "__main__":
    main()
