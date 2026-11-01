"""M6 UI: library page, history and resume, Home dashboard, playlists and queue, privacy controls."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QElapsedTimer, QMimeData, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from fakes import FakeProbe

pytestmark = pytest.mark.ui
LONG = "mock://film?duration=600000"
OTHER = "mock://other?duration=600000"
CLIP = b"\x00" * 64


def mock_factory() -> EngineFactory:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    return factory


def make_window(
    qtbot: QtBot, tmp_path: Path, prefs: Preferences | None = None, db_path: Path | None = None
) -> MainWindow:
    store = PreferencesStore(tmp_path / "settings.json")
    if prefs is not None:
        store.save(prefs)
    service = LibraryService(LibraryDatabase(db_path), FakeProbe, tmp_path / "thumbs")
    win = MainWindow(mock_factory(), load_icon(), engine_name="mock", store=store, library=service)
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    return win


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    win = make_window(qtbot, tmp_path)
    yield win
    win.close()


def play(qtbot: QtBot, window: MainWindow, uri: str) -> MockEngine:
    window.open_path(uri)
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    return engine


def status_text(window: MainWindow) -> str:
    return window.statusBar().currentMessage()


def media_tree(root: Path, names: list[str]) -> Path:
    for i, name in enumerate(names):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(CLIP + name.encode() + bytes([i]))
    return root


def wait_library_idle(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(lambda: not window.library_service.busy, timeout=10_000)
    qtbot.wait(50)  # let queued UI events land


# --------------------------------------------------------- history and resume
def test_position_is_saved_and_resumed(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window, LONG)
    engine.advance(125_000)
    play(qtbot, window, OTHER)  # opening another file saves the first one's place
    entry = window.library_service.db.history_for(LONG)
    assert entry is not None and entry.position_ms == 125_000
    engine = play(qtbot, window, LONG)
    qtbot.waitUntil(lambda: window.controller.status().position_ms == 125_000, timeout=2000)
    assert status_text(window) == "Resumed at 02:05 · Home starts over"
    window.start_over_action.trigger()
    assert window.controller.status().position_ms == 0


def test_short_and_finished_files_start_from_the_beginning(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window, LONG)
    engine.advance(4_000)  # under the 10 s minimum
    play(qtbot, window, OTHER)
    play(qtbot, window, LONG)
    assert window.controller.status().position_ms == 0
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    engine.advance(700_000)  # to the end
    qtbot.waitUntil(lambda: window.player.state is S.ENDED, timeout=2000)
    entry = window.library_service.db.history_for(LONG)
    assert entry is not None and entry.finished
    play(qtbot, window, OTHER)
    play(qtbot, window, LONG)
    assert window.controller.status().position_ms == 0


def test_pause_and_stop_save_the_position(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window, LONG)
    engine.advance(30_000)
    window.player.toggle_play_pause()
    qtbot.waitUntil(lambda: window.player.state is S.PAUSED, timeout=2000)
    assert window.library_service.db.history_for(LONG).position_ms == 30_000  # type: ignore[union-attr]
    window.player.toggle_play_pause()
    engine.advance(20_000)
    window.player.stop()
    assert window.library_service.db.history_for(LONG).position_ms == 50_000  # type: ignore[union-attr]


def test_closing_the_app_saves_the_position(qtbot: QtBot, tmp_path: Path) -> None:
    db_path = tmp_path / "library.db"
    win = make_window(qtbot, tmp_path, db_path=db_path)
    engine = play(qtbot, win, LONG)
    engine.advance(222_000)
    win.close()
    db = LibraryDatabase(db_path)
    entry = db.history_for(LONG)
    assert entry is not None and entry.position_ms == 222_000
    db.close()


def test_history_off_records_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, Preferences(remember_history=False))
    engine = play(qtbot, win, LONG)
    engine.advance(60_000)
    play(qtbot, win, OTHER)
    assert win.library_service.db.history_count() == 0
    win.show_page(win.home)
    assert win.home.history_panel.isHidden()
    win.close()


def test_resume_can_be_turned_off(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, Preferences(resume_playback=False))
    engine = play(qtbot, win, LONG)
    engine.advance(60_000)
    play(qtbot, win, OTHER)
    play(qtbot, win, LONG)
    assert win.controller.status().position_ms == 0
    assert win.library_service.db.history_for(LONG) is not None  # still remembered
    win.close()


def test_home_shows_continue_watching_and_recent(qtbot: QtBot, window: MainWindow) -> None:
    window.show_page(window.home)
    assert window.home.history_panel.isHidden()
    assert not window.home.drop_zone.isHidden()
    engine = play(qtbot, window, LONG)
    engine.advance(300_000)
    play(qtbot, window, OTHER)
    window.show_page(window.home)
    assert not window.home.history_panel.isHidden()
    assert len(window.home.continue_cards) == 1
    card = window.home.continue_cards[0]
    assert "05:00 left" in card.text()
    assert window.home.recent.count() == 2
    card.click()
    assert window.current_page() is window.player
    qtbot.waitUntil(lambda: window.controller.status().position_ms == 300_000, timeout=2000)


def test_forget_and_clear_history(qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = play(qtbot, window, LONG)
    engine.advance(60_000)
    play(qtbot, window, OTHER)
    window.home.forget_requested.emit(LONG)
    assert window.library_service.db.history_for(LONG) is None
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    window.settings.clear_history_button.click()
    assert window.library_service.db.history_count() == 0
    window.show_page(window.home)
    assert window.home.history_panel.isHidden()


def test_clear_history_can_be_declined(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    play(qtbot, window, LONG)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    window.clear_history()
    assert window.library_service.db.history_count() == 1


def test_privacy_settings_round_trip(qtbot: QtBot, window: MainWindow) -> None:
    page = window.settings
    page.remember_history.setChecked(False)
    assert not page.resume_playback.isEnabled()
    assert window.player._prefs.remember_history is False
    page.remember_history.setChecked(True)
    page.resume_playback.setChecked(False)
    assert window.player._prefs.resume_playback is False


# --------------------------------------------------------------- library page
def test_empty_library_explains_and_offers_folders(window: MainWindow) -> None:
    window.show_page(window.library)
    assert window.library.view_stack.currentWidget() is window.library.empty
    assert window.library.empty_action.text() == "Add folder…"
    assert not window.library.scan_button.isEnabled()


def test_add_folder_scans_in_background_and_lists_media(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    root = media_tree(
        tmp_path / "videos", ["Holiday.mp4", "talks/Keynote.mkv", "music/song.flac", "notes.txt"]
    )
    assert window.library.add_folder(str(root))
    wait_library_idle(qtbot, window)
    page = window.library
    assert page.view_stack.currentWidget() is page.view
    names = sorted(e.name for e in page.model.entries)
    assert names == ["Holiday.mp4", "Keynote.mkv", "song.flac"]
    assert "3 files" in page.summary.text()
    assert all(e.probed for e in page.model.entries)
    page.search.setText("talks")
    qtbot.waitUntil(lambda: [e.name for e in page.model.entries] == ["Keynote.mkv"], timeout=2000)
    assert page.summary.text().startswith("1 of 3 files")


def test_duplicate_and_missing_entries_are_flagged(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = tmp_path / "videos"
    root.mkdir()
    (root / "a.mp4").write_bytes(CLIP)
    (root / "a copy.mp4").write_bytes(CLIP)
    (root / "b.mp4").write_bytes(CLIP + b"b")
    window.library.add_folder(str(root))
    wait_library_idle(qtbot, window)
    entries = {e.name: e for e in window.library.model.entries}
    assert entries["a.mp4"].duplicates == 1
    index = window.library.model.index(window.library.model.entries.index(entries["a.mp4"]))
    assert "Same content as" in str(index.data(Qt.ItemDataRole.ToolTipRole))
    (root / "b.mp4").unlink()
    window.library.rescan()
    wait_library_idle(qtbot, window)
    assert not window.library.remove_missing_button.isHidden()
    assert "1 not found" in window.library.summary.text()
    window.library.remove_missing_button.click()
    assert sorted(e.name for e in window.library.model.entries) == ["a copy.mp4", "a.mp4"]
    assert (root / "a.mp4").exists()


def test_playing_from_the_library(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = media_tree(tmp_path / "videos", ["a.mp4", "b.mp4"])
    window.library.add_folder(str(root))
    wait_library_idle(qtbot, window)
    page = window.library
    page.view.activated.emit(page.model.index(0))
    assert window.current_page() is window.player
    assert window.player.controller.status().uri == str((root / "a.mp4").resolve())


def test_context_menu_playlist_and_remove(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = media_tree(tmp_path / "videos", ["a.mp4", "b.mp4", "c.mp4"])
    window.library.add_folder(str(root))
    wait_library_idle(qtbot, window)
    page = window.library
    entries = page.model.entries
    menu = page.build_context_menu(entries[:2])
    texts = [a.text() for a in menu.actions() if a.text()]
    assert texts[0] == "Play 2 files" and "Add to playlist" in texts and "Remove from library" in texts
    pid = page.playlists.new_playlist("Weekend")
    assert pid is not None
    page.add_to_playlist(pid, entries[:2])
    assert [i.title for i in window.library_service.db.playlist_items(pid)] == ["a.mp4", "b.mp4"]
    page.remove_entries([entries[2]])
    assert [e.name for e in page.model.entries] == ["a.mp4", "b.mp4"]
    assert (root / "c.mp4").exists()  # files are never deleted


def test_sort_choice_is_remembered(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path)
    win.library.sort.setCurrentIndex(win.library.sort.findData("size"))
    win.close()
    assert PreferencesStore(tmp_path / "settings.json").load().library_sort == "size"


def test_dropping_a_folder_adds_it_to_the_library(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = media_tree(tmp_path / "dropped", ["x.mp4"])
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(root))])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    assert window.current_page() is window.library
    wait_library_idle(qtbot, window)
    assert [e.name for e in window.library.model.entries] == ["x.mp4"]


def test_scanning_keeps_the_ui_responsive(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = tmp_path / "big"
    for d in range(20):
        folder = root / f"season {d:02d}"
        folder.mkdir(parents=True)
        for i in range(100):
            (folder / f"episode {i:03d}.mkv").write_bytes(CLIP + bytes([d, i]))
    timer, clock = QTimer(), QElapsedTimer()
    gaps: list[int] = []
    clock.start()

    def tick() -> None:
        gaps.append(clock.restart())

    timer.timeout.connect(tick)
    timer.start(10)
    started = time.perf_counter()
    window.library.add_folder(str(root))
    while window.library_service.busy and time.perf_counter() - started < 60:
        QApplication.processEvents()
        time.sleep(0.002)
    timer.stop()
    wait_library_idle(qtbot, window)
    assert window.library_service.db.counts()[0] == 2000
    worst = max(gaps)
    print(f"2000 files: {time.perf_counter() - started:.2f} s, worst UI gap {worst} ms")
    assert worst < 250, f"longest UI gaps (ms): {sorted(gaps)[-5:]} of {len(gaps)} ticks"


# ------------------------------------------------------------- queue (playlist)
def test_playlist_plays_in_order_and_skips_missing(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    missing = str(tmp_path / "gone.mp4")
    window.play_list(["mock://one?duration=1000", missing, "mock://three?duration=1000"])
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=2000)
    assert window.controller.status().uri == "mock://one?duration=1000"
    assert window.next_action.isEnabled() and not window.previous_action.isEnabled()
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    engine.advance(2000)  # ends → next, the missing file is skipped
    qtbot.waitUntil(lambda: window.controller.status().uri == "mock://three?duration=1000", timeout=2000)
    assert "skipped 1 missing" in status_text(window)
    window.previous_action.trigger()
    assert window.controller.status().uri == "mock://one?duration=1000"
    window.next_action.trigger()
    assert window.controller.status().uri == "mock://three?duration=1000"
    assert not window.next_action.isEnabled()  # last item
    window.player.next_in_queue()
    assert status_text(window) == "End of playlist"


def test_opening_a_file_leaves_the_playlist(qtbot: QtBot, window: MainWindow) -> None:
    window.play_list(["mock://one", "mock://two"])
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=2000)
    play(qtbot, window, OTHER)
    assert window.player.queue == ([], -1)
    assert not window.next_action.isEnabled()


def test_playlists_panel_plays_from_selected_item(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = media_tree(tmp_path / "v", ["a.mp4", "b.mp4"])
    db = window.library_service.db
    pid = db.create_playlist("Mix").id
    db.add_to_playlist(pid, [str(root / "a.mp4"), str(root / "b.mp4")])
    panel = window.library.playlists
    panel.refresh(select=pid)
    assert panel.items.count() == 2
    panel.items.setCurrentRow(1)
    panel.down_button.setEnabled(True)
    panel.up_button.click()
    assert [i.title for i in db.playlist_items(pid)] == ["b.mp4", "a.mp4"]
    panel.play_button.click()
    assert window.current_page() is window.player
    assert window.player.queue[1] == 0


def test_damaged_database_is_reported_at_start(qtbot: QtBot, tmp_path: Path) -> None:
    db_path = tmp_path / "library.db"
    db_path.write_bytes(b"not a database" * 500)
    win = make_window(qtbot, tmp_path, db_path=db_path)
    assert "damaged" in status_text(win)
    win.close()
