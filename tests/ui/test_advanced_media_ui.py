"""M8 UI: network stream dialog, chapters, bookmarks, media information and seek previews."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.core.models import EngineCapabilities, MediaInfo, TrackInfo, TrackKind
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.playback.preview import FramePreview, PreviewFrame
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow
from babarify_frame.ui.media_info import media_sections, sections_html, sections_text

pytestmark = pytest.mark.ui
FILM = "mock://film?duration=600000&chapters=4"  # chapters at 0, 150 s, 300 s, 450 s


class FakePreview(FramePreview):
    """Records what the player asks for; returns a solid 16x9 frame."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.requests: list[int] = []
        self.closed = threading.Event()

    def open(self, path: str) -> bool:
        self.opened.append(path)
        return True

    def frame_at(self, position_ms: int) -> PreviewFrame | None:
        self.requests.append(position_ms)
        return PreviewFrame(position_ms, 16, 9, b"\x40\x80\xc0\xff" * 16 * 9)

    def close(self) -> None:
        self.closed.set()


class NoNetworkEngine(MockEngine):
    def get_capabilities(self) -> EngineCapabilities:
        return replace(super().get_capabilities(), network_schemes=frozenset())


def make_window(
    qtbot: QtBot,
    tmp_path: Path,
    engine_class: type[MockEngine] = MockEngine,
    preview: FakePreview | None = None,
    prefs: Preferences | None = None,
) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", engine_class, lambda: EngineProbe("mock", True, "1")))
    store = PreferencesStore(tmp_path / "settings.json")
    if prefs is not None:
        store.save(prefs)
    win = MainWindow(
        factory,
        load_icon(),
        engine_name="mock",
        store=store,
        preview_factory=(lambda: preview) if preview is not None else None,
    )
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


def play(qtbot: QtBot, window: MainWindow, uri: str = FILM) -> MockEngine:
    window.open_path(uri)
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    engine = window.player.controller.engine
    assert isinstance(engine, MockEngine)
    return engine


# ------------------------------------------------------------ network streams
def test_stream_dialog_checks_the_address_while_typing(qtbot: QtBot, window: MainWindow) -> None:
    dialog = window.choose_stream()
    assert dialog is not None
    open_button = dialog.buttons.button(QDialogButtonBox.StandardButton.Open)
    assert not open_button.isEnabled()
    for bad, reason in (
        ("file:///C:/Windows/win.ini", "'file' addresses are not supported"),
        ("http://user:pw@example.com/a.mp4", "Remove the user name and password"),
        ("vlc://quit", "'vlc' addresses"),
    ):
        dialog.address.setText(bad)
        assert not open_button.isEnabled() and reason in dialog.reason.text()
    dialog.address.setText("https://example.com/live/index.m3u8?token=abc")
    assert open_button.isEnabled() and dialog.url == "https://example.com/live/index.m3u8?token=abc"
    dialog.accept()
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    # The title shows the host and file name, never the query string.
    assert "index.m3u8 (example.com)" in window.windowTitle() and "token" not in window.windowTitle()
    assert not window.player.is_seekable  # a live stream (no duration)


def test_stream_failure_is_explained(qtbot: QtBot, window: MainWindow) -> None:
    window.open_path("https://fail.invalid/a.mp4")
    qtbot.waitUntil(lambda: window.player.state is S.ERROR, timeout=3000)
    title, body = window.player.message
    assert "stream could not be played" in title and "fail.invalid" in body


def test_engine_without_network_support_explains_it(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, NoNetworkEngine)
    dialog = win.choose_stream()
    assert dialog is not None and not dialog.address.isEnabled()
    assert "cannot play network streams" in dialog.reason.text()
    win.close()


def test_recent_streams_come_from_history(qtbot: QtBot, window: MainWindow) -> None:
    play(qtbot, window, "https://example.com/show.mp4?duration=120000")
    play(qtbot, window, FILM)
    dialog = window.choose_stream()
    assert dialog is not None and dialog.recent.count() == 1
    assert dialog.recent.item(0).text() == "show.mp4 (example.com)"


# ------------------------------------------------------------ chapters
def test_chapter_navigation_and_marks(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window)
    p = window.player
    assert [c.start_ms for c in p.chapters] == [0, 150_000, 300_000, 450_000]
    assert window.next_chapter_action.isEnabled()
    assert p.controls.seek.marks[0] == (0, 150_000, 300_000, 450_000)
    window.next_chapter_action.trigger()
    assert engine.get_playback_state().position_ms == 150_000
    window.next_chapter_action.trigger()
    assert engine.get_playback_state().position_ms == 300_000
    engine.advance(10_000)  # well into chapter 3: "previous" restarts it
    window.previous_chapter_action.trigger()
    assert engine.get_playback_state().position_ms == 300_000
    window.previous_chapter_action.trigger()  # at its start: goes to chapter 2
    assert engine.get_playback_state().position_ms == 150_000
    window._fill_chapters_menu()
    labels = [a.text() for a in window.chapters_menu.actions()]
    assert labels == ["00:00  Part 1", "02:30  Part 2", "05:00  Part 3", "07:30  Part 4"]
    checked = [a.isChecked() for a in window.chapters_menu.actions()]
    assert checked == [False, True, False, False]
    window.chapters_menu.actions()[3].trigger()
    assert engine.get_playback_state().position_ms == 450_000


def test_no_chapter_actions_without_chapters(qtbot: QtBot, window: MainWindow) -> None:
    play(qtbot, window, "mock://plain?duration=600000")
    assert not window.next_chapter_action.isEnabled() and not window.chapters_menu.isEnabled()


# ------------------------------------------------------------ bookmarks
def test_bookmarks_add_jump_rename_delete(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window)
    engine.advance(42_000)
    window.add_bookmark_action.trigger()
    engine.advance(60_000)
    window.add_bookmark_action.trigger()
    p = window.player
    assert [b.position_ms for b in p.bookmarks] == [42_000, 102_000]
    assert p.controls.seek.marks[1] == (42_000, 102_000)
    dialog = window.show_bookmarks()
    assert dialog.list.count() == 2 and dialog.list.item(0).text() == "00:42"
    dialog.list.setCurrentRow(0)
    dialog.jump_button.click()
    assert engine.get_playback_state().position_ms == 42_000
    dialog.rename_requested.emit(p.bookmarks[0].id, "Opening  scene")
    assert dialog.list.item(0).text() == "00:42  Opening scene"
    dialog.list.setCurrentRow(1)
    dialog.delete_button.click()
    assert [b.label for b in p.bookmarks] == ["Opening scene"] and dialog.list.count() == 1
    # Bookmarks belong to the file: another file has none, coming back shows them again.
    play(qtbot, window, "mock://other?duration=600000")
    assert p.bookmarks == [] and dialog.list.count() == 0
    play(qtbot, window)
    assert [b.label for b in p.bookmarks] == ["Opening scene"]


def test_bookmarks_need_a_seekable_file(qtbot: QtBot, window: MainWindow) -> None:
    play(qtbot, window, "https://example.com/live")  # live: no duration
    assert not window.add_bookmark_action.isEnabled()
    assert window.player.add_bookmark() is None


# ------------------------------------------------------------ media information
def test_media_information_lists_tracks_tags_and_chapters(qtbot: QtBot, window: MainWindow) -> None:
    play(qtbot, window)
    dialog = window.show_media_info()
    text = dialog.text
    for expected in (
        "Duration: 10:00",
        "Title: Mock title",
        "Size: 1920 × 1080",  # noqa: RUF001
        "Frame rate: 30 fps",
        "Channels: stereo",
        "Sample rate: 48,000 Hz",
        "Audio 2",
        "Subtitle 2",
        "02:30: Part 2",
    ):
        assert expected in text, expected
    dialog.copy_button.click()
    assert dialog.copy_button.text() == "Copied"


def test_untrusted_tags_are_escaped_and_shortened(tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"\x00" * 2048)
    info = MediaInfo(
        uri=str(media),
        duration_ms=8000,
        metadata=(("Title", '<img src="x" onerror="alert(1)">'), ("Description", "x" * 1000)),
        tracks=(TrackInfo(1, TrackKind.AUDIO, title="<b>bold</b>", codec="aac"),),
    )
    sections = media_sections(info, str(media))
    html = sections_html(sections)
    assert "<img" not in html and "&lt;img" in html and "<b>bold" not in html
    text = sections_text(sections)
    assert (
        "Size: 2.0 KB (2,048 bytes)" in text
        and "Overall bitrate: 2 kb/s" in text
        and "Container: MP4" in text
    )
    assert max(len(line) for line in text.splitlines()) < 320


def test_stream_information_hides_the_query(tmp_path: Path) -> None:
    sections = media_sections(MediaInfo(uri="x"), "https://cdn.example.com/a/live.m3u8?token=SECRET")
    text = sections_text(sections)
    assert "SECRET" not in text and "Address: https://cdn.example.com/a/live.m3u8" in text
    assert "Duration: live / unknown" in text


# ------------------------------------------------------------ seek previews
def test_hovering_the_seek_bar_shows_time_chapter_and_picture(qtbot: QtBot, tmp_path: Path) -> None:
    preview = FakePreview()
    media = tmp_path / "film.mp4"
    media.write_bytes(b"\x00")
    win = make_window(qtbot, tmp_path, preview=preview)
    win.open_path(str(media))
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    qtbot.waitUntil(lambda: len(preview.opened) == 1, timeout=3000)
    assert Path(preview.opened[0]).resolve() == media.resolve()
    seek = win.player.controls.seek
    position = seek.maximum() // 2
    seek.hovered.emit(position, seek.mapToGlobal(QPoint(seek.x_of(position), 0)))
    popup = win.player._popup
    assert popup.isVisible() and popup.text.text() == "00:30"
    qtbot.waitUntil(lambda: popup.image.isVisible(), timeout=3000)
    assert popup.image.pixmap().width() == 16
    assert preview.requests and abs(preview.requests[0] - position) <= 1000
    seek.hover_left.emit()
    assert not popup.isVisible()
    win.close()
    assert preview.closed.wait(5)


def test_no_preview_source_for_streams_or_when_switched_off(qtbot: QtBot, tmp_path: Path) -> None:
    preview = FakePreview()
    win = make_window(qtbot, tmp_path, preview=preview, prefs=Preferences(seek_previews=False))
    media = tmp_path / "film.mp4"
    media.write_bytes(b"\x00")
    win.open_path(str(media))
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    win.open_path("https://example.com/show.mp4?duration=120000")
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    seek = win.player.controls.seek
    seek.hovered.emit(5000, seek.mapToGlobal(QPoint(10, 0)))
    assert win.player._popup.text.text() == "00:05" and not win.player._popup.image.isVisible()
    qtbot.wait(200)
    assert preview.opened == [] and preview.requests == []
    win.close()
