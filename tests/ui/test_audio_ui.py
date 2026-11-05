"""The audio screen, repeat, shuffle, the queue and the sleep timer, against the mock engine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.core.music import RepeatMode, VisualStyle
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.audio_view import colour_from
from babarify_frame.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


def make_window(qtbot: QtBot, tmp_path: Path) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1.0")))
    store = PreferencesStore(tmp_path / "settings.json")
    win = MainWindow(factory, load_icon(), engine_name="mock", store=store)
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


def song(tmp_path: Path, name: str, data: bytes = b"audio") -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def png_mp3(tmp_path: Path, name: str) -> str:
    """A tiny MP3-shaped file holding a real picture."""
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(QColor("#C04020"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    picture = bytes(buffer.data().data())
    body = b"\0image/png\0\x03\0" + picture
    frame = b"APIC" + len(body).to_bytes(4, "big") + b"\0\0" + body
    size = len(frame)
    header = b"ID3\x03\0\0" + bytes((size >> shift) & 0x7F for shift in (21, 14, 7, 0))
    return song(tmp_path, name, header + frame + b"\xff\xfbaudio")


def test_a_song_gets_the_audio_screen_not_a_black_video(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    player = window.player
    player.open_path(song(tmp_path, "My Song.mp3"))
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    assert player._stage.currentWidget() is player.audio_view
    # The mock reports tags, as a real file's would.
    qtbot.waitUntil(lambda: player.audio_view.title.text() == "Mock title")
    assert player.audio_view.artist.text() == "Mock artist"


def test_a_video_keeps_the_video_surface(qtbot: QtBot, window: MainWindow) -> None:
    player = window.player
    player.open_path("mock://clip?duration=60000")
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    assert player._stage.currentWidget() is player.video


def test_no_picture_shows_the_animation_and_it_moves_only_while_playing(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows can have animations switched off, as test machines may: that has its own test below.
    monkeypatch.setattr("babarify_frame.ui.audio_view.animations_allowed", lambda: True)
    player = window.player
    window.show_page(player)
    player.open_path(song(tmp_path, "plain.mp3"))
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    view = player.audio_view
    assert not view.showing_picture
    qtbot.waitUntil(lambda: view.visualizer.animating)
    player.toggle_play_pause()
    qtbot.waitUntil(lambda: not view.visualizer.animating)


def test_the_animation_stands_still_if_windows_has_animations_off(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("babarify_frame.ui.audio_view.animations_allowed", lambda: False)
    player = window.player
    window.show_page(player)
    player.open_path(song(tmp_path, "plain.mp3"))
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    qtbot.wait(200)
    assert player.audio_view.visualizer.isVisible()
    assert not player.audio_view.visualizer.animating


def test_a_picture_in_the_file_is_shown_instead(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    window.show_page(player)
    player.open_path(png_mp3(tmp_path, "cover.mp3"))
    qtbot.waitUntil(lambda: player.audio_view.showing_picture, timeout=3000)
    assert not player.audio_view.visualizer.isVisible()


def test_the_screens_colour_comes_from_the_picture_and_stays_dark() -> None:
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("#FFEE00"))
    colour = colour_from(image)
    assert colour.valueF() <= 0.31
    assert 0.1 < colour.hueF() < 0.2  # Still recognisably yellow.


@pytest.mark.parametrize("style", [s for s in VisualStyle if s is not VisualStyle.AUTO])
def test_every_animation_draws(qtbot: QtBot, window: MainWindow, tmp_path: Path, style: VisualStyle) -> None:
    player = window.player
    window.show_page(player)
    player.open_path(song(tmp_path, "plain.mp3"))
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    visualizer = player.audio_view.visualizer
    window._choose_animation(style)
    qtbot.waitUntil(lambda: visualizer.shown_style is style, timeout=3000)
    qtbot.wait(500)  # It fades in after changing.
    picture = visualizer.grab().toImage()
    assert not picture.isNull()
    colours = {
        picture.pixelColor(x, y).rgb()
        for x in range(0, picture.width(), 9)
        for y in range(0, picture.height(), 9)
    }
    assert len(colours) > 3, "it drew something"


def test_a_chosen_animation_is_remembered(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    window._choose_animation(VisualStyle.CIRCLE)
    assert PreferencesStore(tmp_path / "settings.json").load().visual_style == "circle"
    assert window.settings.visual_style.currentData() == "circle"


def test_choosing_an_animation_in_settings_applies_it(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    combo = window.settings.visual_style
    combo.setCurrentIndex(combo.findData("lights"))
    assert window.player.audio_view.visualizer.style_choice is VisualStyle.LIGHTS
    assert PreferencesStore(tmp_path / "settings.json").load().visual_style == "lights"


def test_repeat_is_remembered(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    window.player.cycle_repeat()
    assert window.player.repeat_mode is RepeatMode.ONE
    assert window.player.controls.repeat_button.accessibleName() == "Repeating this file"
    assert PreferencesStore(tmp_path / "settings.json").load().repeat_mode == "one"


def engine_of(window: MainWindow) -> MockEngine:
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    return engine


def end_current(qtbot: QtBot, window: MainWindow) -> None:
    engine = engine_of(window)
    engine.advance(10_000_000)


def test_repeat_one_plays_the_file_again(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    path = song(tmp_path, "a.mp3")
    player.cycle_repeat()
    player.open_path(path)
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    end_current(qtbot, window)
    qtbot.waitUntil(lambda: player.state is S.PLAYING and player.current_uri == path, timeout=3000)


def test_repeat_off_stops_at_the_end(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    player.open_path(song(tmp_path, "a.mp3"))
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    end_current(qtbot, window)
    qtbot.waitUntil(lambda: player.state is S.ENDED)
    qtbot.wait(200)
    assert player.state is S.ENDED


def test_repeat_all_goes_round_the_list(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    paths = [song(tmp_path, f"{n}.mp3") for n in "ab"]
    player.cycle_repeat()
    player.cycle_repeat()
    player.play_queue(paths, 1)
    qtbot.waitUntil(lambda: player.state is S.PLAYING and player.current_uri == paths[1])
    assert player.can_go_next
    end_current(qtbot, window)
    qtbot.waitUntil(lambda: player.current_uri == paths[0] and player.state is S.PLAYING, timeout=3000)


def test_shuffle_keeps_the_song_and_turns_back(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    paths = [song(tmp_path, f"{n}.mp3") for n in "abcdefgh"]
    player.play_queue(paths, 2)
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    player.toggle_shuffle()
    assert player.shuffle_on
    queue, index = player.queue
    assert queue[index] == paths[2] and sorted(queue) == sorted(paths)
    assert player.controls.shuffle_button.accessibleName() == "Shuffle is on"
    player.toggle_shuffle()
    assert not player.shuffle_on
    assert player.queue == (paths, 2)


def test_shuffle_needs_a_list(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    player.open_path(song(tmp_path, "a.mp3"))
    player.toggle_shuffle()
    assert not player.shuffle_on


def test_list_buttons_show_only_with_a_list(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    window.show_page(player)
    window.resize(1200, 800)
    controls = player.controls
    player.open_path(song(tmp_path, "a.mp3"))
    assert not controls.next_button.isVisible() and not controls.queue_button.isVisible()
    player.play_queue([song(tmp_path, "b.mp3"), song(tmp_path, "c.mp3")])
    qtbot.waitUntil(controls.next_button.isVisible)
    assert controls.shuffle_button.isVisible() and controls.queue_button.isVisible()


def test_choosing_from_the_queue_jumps_there(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    paths = [song(tmp_path, f"{n}.mp3") for n in "abc"]
    player.play_queue(paths)
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    player.play_queue_item(2)
    qtbot.waitUntil(lambda: player.current_uri == paths[2])
    assert player.queue[1] == 2


def test_sleep_timer_pauses_and_can_be_cancelled(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    player.open_path(song(tmp_path, "a.mp3"))
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    player.set_sleep_timer(30)
    assert player.sleep_remaining_ms is not None
    player.set_sleep_timer(None)
    assert player.sleep_remaining_ms is None
    player.set_sleep_timer(30)
    player._sleep_timer.timeout.emit()
    qtbot.waitUntil(lambda: player.state is S.PAUSED)


def test_full_screen_keeps_the_controls_for_audio(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    player = window.player
    window.show_page(player)
    player.open_path(song(tmp_path, "a.mp3"))
    qtbot.waitUntil(lambda: player.state is S.PLAYING)
    player.set_fullscreen_mode(True)
    player._idle_ms = 60_000
    player._poll_cursor()
    assert not player.controls_hidden
    player.set_fullscreen_mode(False)
