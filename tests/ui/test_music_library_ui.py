"""The Library's music tabs, favourites and automatic lists, against the mock engine."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.library.database import LibraryDatabase, ProbeRecord, ScanRecord
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.playback.media_probe import MediaProbe, ProbeResult
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.music_panel import EditDetailsDialog

pytestmark = pytest.mark.ui


class TaggingProbe(MediaProbe):
    """Reports tags from the file's name: "Title - Artist - Album.mp3"."""

    name = "tagging"

    def probe(self, path: str, cancel: threading.Event) -> ProbeResult | None:
        parts = Path(path).stem.split(" - ")
        tags = (*parts, None, None, None)[:3]
        return ProbeResult(180_000, None, None, None, "mp3", title=tags[0], artist=tags[1], album=tags[2])


def add_song(
    db: LibraryDatabase, folder: int, path: Path, title: str, artist: str | None, album: str | None
) -> str:
    path.write_bytes(b"audio")
    db.upsert_media([ScanRecord(str(path), folder, 5, 1.0, None)], time.time())
    entry = db.media_by_path(str(path))
    assert entry is not None
    db.set_probe_result(entry.id, ProbeRecord(180_000, None, None, None, "mp3", None, title, artist, album))
    return str(path)


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1.0")))
    service = LibraryService(LibraryDatabase(None), TaggingProbe, thumbnail_dir=tmp_path / "thumbnails")
    win = MainWindow(
        factory,
        load_icon(),
        engine_name="mock",
        store=PreferencesStore(tmp_path / "settings.json"),
        library=service,
    )
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    yield win
    win.close()


@pytest.fixture
def songs(window: MainWindow, tmp_path: Path) -> list[str]:
    db = window.library_service.db
    folder = db.add_folder(str(tmp_path)).id
    return [
        add_song(db, folder, tmp_path / "1.mp3", "Golden Sky", "Lucas", "Horizons"),
        add_song(db, folder, tmp_path / "2.mp3", "Sailor Moon", "Mira", "Horizons"),
        add_song(db, folder, tmp_path / "3.mp3", "Black Suit", "Dan", "Night Drive"),
    ]


def open_tab(window: MainWindow, name: str) -> None:
    window.show_page(window.library)
    tabs = window.library.tabs
    tabs.setCurrentIndex([tabs.tabText(i) for i in range(tabs.count())].index(name))


def test_the_library_has_music_tabs(qtbot: QtBot, window: MainWindow, songs: list[str]) -> None:
    open_tab(window, "Songs")
    panel = window.library.songs_panel
    assert [e.title for e in panel.songs.entries] == ["Black Suit", "Golden Sky", "Sailor Moon"]
    assert panel.summary.text() == "3 songs"
    open_tab(window, "Albums")
    assert [g.title for g in window.library.albums_panel.groups.groups] == ["Horizons", "Night Drive"]
    open_tab(window, "Artists")
    assert [g.title for g in window.library.artists_panel.groups.groups] == ["Dan", "Lucas", "Mira"]


def test_one_song_reads_properly(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    db = window.library_service.db
    add_song(db, db.add_folder(str(tmp_path)).id, tmp_path / "a.mp3", "One", "A", "B")
    open_tab(window, "Songs")
    assert window.library.songs_panel.summary.text() == "1 song"


def test_tapping_a_song_plays_the_list_from_there(qtbot: QtBot, window: MainWindow, songs: list[str]) -> None:
    open_tab(window, "Songs")
    panel = window.library.songs_panel
    panel.play_from(1)  # Golden Sky, second by title.
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING)
    queue, index = window.player.queue
    assert queue[index] == songs[0]
    assert len(queue) == 3


def test_opening_an_album_shows_and_plays_its_songs(
    qtbot: QtBot, window: MainWindow, songs: list[str]
) -> None:
    open_tab(window, "Albums")
    panel = window.library.albums_panel
    panel.open_group(panel.groups.groups[0])
    assert panel.stack.currentWidget() is panel.songs_view
    assert not panel.back_button.isHidden()
    assert sorted(e.title for e in panel.songs.entries) == ["Golden Sky", "Sailor Moon"]
    assert "Horizons" in panel.summary.text()
    panel.play_all()
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING)
    assert len(window.player.queue[0]) == 2
    panel.close_group()
    assert panel.stack.currentWidget() is panel.groups_view
    assert panel.back_button.isHidden()


def test_shuffle_plays_everything_in_a_random_order(
    qtbot: QtBot, window: MainWindow, songs: list[str]
) -> None:
    open_tab(window, "Songs")
    window.library.songs_panel.shuffle_all()
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING)
    assert window.player.shuffle_on
    assert sorted(window.player.queue[0]) == sorted(songs)


def test_search_filters_songs_and_says_when_nothing_matches(
    qtbot: QtBot, window: MainWindow, songs: list[str]
) -> None:
    open_tab(window, "Songs")
    panel = window.library.songs_panel
    panel.search.setText("mira")
    panel.refresh()
    assert [e.title for e in panel.songs.entries] == ["Sailor Moon"]
    panel.search.setText("zzz")
    panel.refresh()
    assert panel.stack.currentWidget() is panel.empty
    assert "search" in panel.empty.text()
    assert not panel.play_button.isEnabled()


def test_an_empty_library_says_what_to_do(qtbot: QtBot, window: MainWindow) -> None:
    open_tab(window, "Artists")
    panel = window.library.artists_panel
    assert panel.stack.currentWidget() is panel.empty
    assert "Folders" in panel.empty.text()


def test_the_heart_adds_the_song_to_favourites(qtbot: QtBot, window: MainWindow, songs: list[str]) -> None:
    player = window.player
    window.show_page(player)
    player.open_path(songs[0])
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    button = player.controls.favourite_button
    assert button.isVisible() and button.accessibleName() == "Add to favourites"
    button.click()
    assert player.is_favourite
    assert button.accessibleName() == "Remove from favourites"
    assert window.library_service.db.is_favourite(songs[0])
    button.click()
    assert not window.library_service.db.is_favourite(songs[0])


def test_a_video_has_no_heart(qtbot: QtBot, window: MainWindow) -> None:
    player = window.player
    window.show_page(player)
    player.open_path("mock://clip?duration=60000")
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    assert not player.controls.favourite_button.isVisible()


def test_a_songs_menu_adds_favourites(qtbot: QtBot, window: MainWindow, songs: list[str]) -> None:
    open_tab(window, "Songs")
    panel = window.library.songs_panel
    entry = panel.songs.entries[0]
    menu = panel.build_context_menu([entry])
    labels = [action.text() for action in menu.actions()]
    assert "Add to favourites" in labels and "Add to playlist" in labels
    next(action for action in menu.actions() if action.text() == "Add to favourites").trigger()
    assert window.library_service.db.is_favourite(entry.path)
    labels = [action.text() for action in panel.build_context_menu([entry]).actions()]
    assert "Remove from favourites" in labels


def test_a_songs_menu_lines_it_up_and_hides_it(qtbot: QtBot, window: MainWindow, songs: list[str]) -> None:
    open_tab(window, "Songs")
    panel = window.library.songs_panel
    first, second, third = panel.songs.entries[:3]

    def choose(entry: object, text: str) -> None:
        next(a for a in panel.build_context_menu([entry]).actions() if a.text() == text).trigger()

    choose(first, "Add to queue")  # nothing playing: it just plays
    qtbot.waitUntil(lambda: window.player.queue == ([first.path], 0), timeout=5000)
    choose(second, "Add to queue")
    choose(third, "Play next")
    assert window.player.queue == ([first.path, third.path, second.path], 0)
    choose(first, "Hide")
    assert first.path not in [entry.path for entry in panel.songs.entries]
    assert window.library_service.db.hidden_media() == [first.path]


def test_the_for_you_tab_shows_the_recap_and_plays(
    qtbot: QtBot, window: MainWindow, songs: list[str]
) -> None:
    open_tab(window, "For you")
    panel = window.library.for_you
    assert "Play some songs" in panel.summary.text()
    assert panel.never_played.count() > 0
    entry = window.library_service.db.songs()[0]
    window.library_service.db.record_play(entry.path, entry.display_title, 1000)
    window.library.refresh_current_tab()
    assert "1 song 1 time" in panel.summary.text()
    assert panel.most_played.count() == 1
    received: list[list[str]] = []
    panel.play_requested.connect(lambda paths, _start: received.append(paths))
    panel.most_played.itemActivated.emit(panel.most_played.item(0))
    assert received == [[entry.path]]


def test_a_songs_details_can_be_edited(qtbot: QtBot, window: MainWindow, songs: list[str]) -> None:
    open_tab(window, "Songs")
    panel = window.library.songs_panel
    entry = panel.songs.entries[0]
    assert "Edit details…" in [a.text() for a in panel.build_context_menu([entry]).actions()]
    assert "Edit details…" not in [
        a.text() for a in panel.build_context_menu(panel.songs.entries[:2]).actions()
    ]
    dialog = EditDetailsDialog(window.library_service, entry, window)
    qtbot.addWidget(dialog)
    dialog.title_box.setText("A better title")
    dialog.save()
    panel.refresh()
    assert "A better title" in [e.title for e in panel.songs.entries]


def test_automatic_lists_show_and_play(qtbot: QtBot, window: MainWindow, songs: list[str]) -> None:
    db = window.library_service.db
    db.set_favourite(songs[1], "Sailor Moon", True)
    open_tab(window, "Playlists")
    panel = window.library.playlists
    assert [panel.automatic.item(i).text() for i in range(panel.automatic.count())] == [
        "Favourites",
        "Recently played",
        "Most played",
        "Recently added",
    ]
    panel.automatic.setCurrentRow(0)
    assert panel.current_automatic == "Favourites"
    assert [panel.items.item(i).text() for i in range(panel.items.count())] == ["Sailor Moon"]
    assert not panel.up_button.isEnabled() and not panel.rename_button.isEnabled()
    panel.items.setCurrentRow(0)
    panel.remove_button.click()
    assert not db.is_favourite(songs[1])
    assert panel.current_automatic == "Favourites", "the list stays open after removing from it"
    panel.automatic.setCurrentRow(3)
    assert panel.items.count() == 3
    assert not panel.remove_button.isEnabled()
    panel.play_button.click()
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING)
    assert len(window.player.queue[0]) == 3


def test_choosing_your_own_playlist_leaves_the_automatic_one(
    qtbot: QtBot, window: MainWindow, songs: list[str]
) -> None:
    db = window.library_service.db
    playlist = db.create_playlist("Mine")
    db.add_to_playlist(playlist.id, [songs[0]])
    open_tab(window, "Playlists")
    panel = window.library.playlists
    panel.automatic.setCurrentRow(3)
    assert panel.current_automatic == "Recently added"
    panel.playlists.setCurrentRow(0)
    assert panel.current_automatic is None
    assert panel.current_playlist == playlist.id
    assert panel.items.count() == 1
    assert panel.up_button.isEnabled() and panel.rename_button.isEnabled()


def test_scanning_reads_tags_and_a_songs_picture(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(QColor("#C04020"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    body = b"\0image/png\0\x03\0" + bytes(buffer.data().data())
    frame = b"APIC" + len(body).to_bytes(4, "big") + b"\0\0" + body
    size = bytes((len(frame) >> shift) & 0x7F for shift in (21, 14, 7, 0))
    (music / "Golden Sky - Lucas - Horizons.mp3").write_bytes(
        b"ID3\x03\0\0" + size + frame + b"\xff\xfbaudio"
    )
    (music / "Plain - Mira - Other.mp3").write_bytes(b"\xff\xfbaudio")
    window.show_page(window.library)
    window.library.add_folder(str(music))
    qtbot.waitUntil(
        lambda: not window.library_service.busy and len(window.library_service.db.songs()) == 2, timeout=8000
    )
    qtbot.waitUntil(lambda: not window.library_service.db.counts()[2], timeout=8000)
    found = {e.title: e for e in window.library_service.db.songs()}
    assert found["Golden Sky"].artist == "Lucas" and found["Golden Sky"].album == "Horizons"
    assert found["Golden Sky"].thumbnail, "its picture became its thumbnail"
    assert found["Plain"].thumbnail is None


def test_existing_songs_are_read_again_when_the_app_starts(qtbot: QtBot, tmp_path: Path) -> None:
    database = LibraryDatabase(None)
    folder = database.add_folder(str(tmp_path)).id
    song = tmp_path / "Old - Artist - Album.mp3"
    song.write_bytes(b"x")
    database.upsert_media([ScanRecord(str(song), folder, 1, 1.0, None)], time.time())
    assert database.counts()[2] == 1
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1.0")))
    win = MainWindow(
        factory,
        load_icon(),
        engine_name="mock",
        store=PreferencesStore(tmp_path / "settings.json"),
        library=LibraryService(database, TaggingProbe),
    )
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: database.counts()[2] == 0, timeout=8000)
    assert database.songs()[0].title == "Old"
    win.close()
