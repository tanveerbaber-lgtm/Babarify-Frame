"""M7 UI: Picture & Sound panel, rotation restart, profiles, volume boost, A-B repeat, frames, snapshots."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.core.enhancements import EqualizerSettings, PictureSettings, VideoTransform
from babarify_frame.core.models import EngineCapabilities, EngineOptions
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow

pytestmark = pytest.mark.ui
FILM = "mock://film?duration=600000"


class LibVlcLikeEngine(MockEngine):
    """Mock with libVLC's M7 profile under hardware decoding: no gamma, rotation needs a restart."""

    def get_capabilities(self) -> EngineCapabilities:
        caps = super().get_capabilities()
        return replace(
            caps,
            picture_adjustments=caps.picture_adjustments - {"gamma"},
            rotation="restart",
        )


class NoEqualizerEngine(MockEngine):
    def get_capabilities(self) -> EngineCapabilities:
        return replace(super().get_capabilities(), supports_equalizer=False, supports_crop=False)


def factory_for(engine_class: type[MockEngine]) -> EngineFactory:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", engine_class, lambda: EngineProbe("mock", True, "1")))
    return factory


def make_window(
    qtbot: QtBot,
    tmp_path: Path,
    engine_class: type[MockEngine] = MockEngine,
    prefs: Preferences | None = None,
) -> MainWindow:
    store = PreferencesStore(tmp_path / "settings.json")
    if prefs is not None:
        store.save(prefs)
    win = MainWindow(factory_for(engine_class), load_icon(), engine_name="mock", store=store)
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
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    return engine


def status_text(window: MainWindow) -> str:
    return window.statusBar().currentMessage()


# ------------------------------------------------------------------- picture
def test_picture_sliders_apply_live_and_persist(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    engine = play(qtbot, window)
    panel = window.show_enhancements()
    panel.picture_sliders["brightness"].setValue(140)
    panel.picture_sliders["hue"].setValue(-45)
    assert engine.picture.brightness == 1.4 and engine.picture.hue == -45.0
    assert panel.picture_values["brightness"].text() == "140 %"
    assert engine.get_playback_state().state is S.PLAYING
    saved = PreferencesStore(tmp_path / "settings.json").load()
    assert saved.picture.brightness == 1.4
    panel.picture_resets["brightness"].click()
    assert engine.picture.brightness == 1.0
    panel.reset_picture_button.click()
    assert engine.picture == PictureSettings()


def test_picture_is_reapplied_to_a_new_engine(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, prefs=Preferences(picture=PictureSettings(saturation=0.0)))
    engine = play(qtbot, win)
    assert engine.picture.saturation == 0.0
    win.close()


def test_unsupported_gamma_is_disabled_and_explained(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, LibVlcLikeEngine, Preferences(picture=PictureSettings(gamma=1.5)))
    engine = play(qtbot, win)
    assert engine.picture.gamma == 1.0  # a saved unsupported value is not forced on the engine
    panel = win.show_enhancements()
    assert not panel.picture_sliders["gamma"].isEnabled()
    assert "gamma" in panel.picture_note.text()
    assert panel.picture_sliders["brightness"].isEnabled()
    win.close()


def test_unsupported_equalizer_and_crop_are_disabled(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, NoEqualizerEngine)
    play(qtbot, win)
    panel = win.show_enhancements()
    assert not panel.eq_enabled.isEnabled() and not panel.eq_preset.isEnabled()
    assert "not supported" in panel.audio_note.text()
    assert not panel.crop.isEnabled() and "crop" in panel.video_note.text().lower()
    assert panel.aspect.isEnabled()
    win.close()


# ---------------------------------------------------------------- equalizer
def test_equalizer_presets_and_custom_bands(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    engine = play(qtbot, window)
    panel = window.show_enhancements()
    assert [panel.eq_preset.itemText(i) for i in range(panel.eq_preset.count())] == [
        "Custom", "Flat", "Rock", "Classical",
    ]  # fmt: skip
    assert panel.eq_labels[5].text() == "1k"
    panel.eq_preset.setCurrentIndex(panel.eq_preset.findText("Rock"))
    panel.eq_preset.activated.emit(panel.eq_preset.currentIndex())
    assert engine.equalizer.enabled and engine.equalizer.preset == "Rock"
    assert engine.equalizer.bands_db == (4.0,) * 10
    panel.eq_sliders[0].setValue(-6)
    assert engine.equalizer.bands_db[0] == -6.0
    assert panel.eq_preset.currentText() == "Custom" and engine.equalizer.preset == ""
    panel.reset_eq_button.click()
    assert engine.equalizer == EqualizerSettings()
    assert not panel.eq_sliders[0].isEnabled()  # off: the bands are greyed
    assert PreferencesStore(tmp_path / "settings.json").load().equalizer == EqualizerSettings()


# -------------------------------------------------------- aspect, crop, zoom
def test_geometry_applies_and_resets_for_the_next_file(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window)
    panel = window.show_enhancements()
    panel.aspect.setCurrentIndex(panel.aspect.findData("4:3"))
    panel.zoom.setCurrentIndex(panel.zoom.findData(2.0))
    assert engine.geometry == ("4:3", "", 2.0)
    play(qtbot, window, "mock://other?duration=600000")
    engine = window.controller.engine
    assert isinstance(engine, MockEngine)
    assert engine.geometry == ("", "", 0.0)
    assert window.player.video_geometry == ("", "", 0.0)


# ----------------------------------------------------------------- rotation
def test_live_rotation(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window)
    panel = window.show_enhancements()
    panel.rotation.setCurrentIndex(panel.rotation.findData("90"))
    assert engine.transform is VideoTransform.ROTATE_90
    assert window.controller.engine is engine  # no restart needed


def test_restart_rotation_keeps_position_and_settings(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, LibVlcLikeEngine)
    engine = play(qtbot, win)
    engine.advance(42_000)
    panel = win.show_enhancements()
    panel.picture_sliders["contrast"].setValue(150)
    assert "restarts playback" in panel.video_note.text()
    panel.rotation.setCurrentIndex(panel.rotation.findData("180"))
    qtbot.waitUntil(lambda: win.player.engine_is_ready and win.controller.engine is not engine, timeout=5000)
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=3000)
    new = win.controller.engine
    assert isinstance(new, MockEngine)
    assert new.options.video_transform is VideoTransform.ROTATE_180
    assert win.controller.status().position_ms == 42_000
    assert new.picture.contrast == 1.5
    assert panel.rotation.currentData() == "180"
    win.close()


# ----------------------------------------------------------------- profiles
def test_profiles_save_apply_delete_and_persist(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = play(qtbot, window)
    panel = window.show_enhancements()
    panel.picture_sliders["brightness"].setValue(70)
    panel.eq_enabled.setChecked(True)
    panel.eq_sliders[0].setValue(8)
    assert panel.save_profile("Night") is not None
    panel.reset_all_button.click()
    assert engine.picture == PictureSettings() and engine.equalizer == EqualizerSettings()
    panel.profile_list.setCurrentRow(0)
    panel.apply_profile_button.click()
    assert engine.picture.brightness == 0.7
    assert engine.equalizer.enabled and engine.equalizer.bands_db[0] == 8.0
    saved = PreferencesStore(tmp_path / "settings.json").load()
    assert [p.name for p in saved.profiles] == ["Night"]
    panel.save_profile("night")  # same name: replaced, not duplicated
    assert panel.profile_list.count() == 1
    panel.profile_list.setCurrentRow(0)
    panel.delete_profile_button.click()
    assert PreferencesStore(tmp_path / "settings.json").load().profiles == ()


# -------------------------------------------------------------- volume boost
def test_volume_boost_is_opt_in_capped_and_never_remembered(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    engine = play(qtbot, window)
    window.player.set_volume(100)
    window.player.step_volume(5)
    assert window.controller.status().volume == 100  # no boost by default
    window.settings.allow_boost.setChecked(True)
    assert window.player.controls.volume.maximum() == 150
    for _ in range(20):
        window.player.step_volume(5)
    assert window.controller.status().volume == 150
    assert window.player.controls.volume.property("boost") is True
    assert "distort" in window.player.controls.volume.toolTip()
    window.close()
    assert PreferencesStore(tmp_path / "settings.json").load().volume == 100
    assert engine.get_playback_state().state is S.CLOSED


def test_turning_boost_off_brings_volume_back(qtbot: QtBot, window: MainWindow) -> None:
    play(qtbot, window)
    window.settings.allow_boost.setChecked(True)
    window.player.set_volume(140)
    window.settings.allow_boost.setChecked(False)
    assert window.controller.status().volume == 100
    assert window.player.controls.volume.maximum() == 100


# ------------------------------------------------------------- A-B, frames, snapshot
def test_ab_repeat(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window)
    window.show_page(window.player)
    engine.advance(10_000)
    window.ab_action.trigger()
    assert window.player.ab_loop == (10_000, None)
    engine.advance(10_200)
    window.ab_action.trigger()
    assert window.player.ab_loop == (10_000, 20_200)
    assert window.controller.status().position_ms == 10_000  # jumps back to A
    engine.advance(10_500)
    qtbot.waitUntil(lambda: window.controller.status().position_ms < 15_000, timeout=2000)
    window.ab_action.trigger()
    assert window.player.ab_loop == (None, None) and status_text(window) == "Repeat off"


def test_ab_requires_b_after_a(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window)
    window.show_page(window.player)
    engine.advance(10_000)
    window.ab_action.trigger()
    window.ab_action.trigger()  # same place
    assert window.player.ab_loop == (10_000, None)
    assert status_text(window) == "B must be later than A"


def test_frame_step_and_unsupported_back_step(qtbot: QtBot, window: MainWindow) -> None:
    play(qtbot, window)
    window.show_page(window.player)
    assert window.next_frame_action.isEnabled()
    assert not window.previous_frame_action.isEnabled()  # mock, like libVLC 3: forward only
    window.next_frame_action.trigger()
    assert window.player.state is S.PAUSED
    assert status_text(window) == "Next frame"
    window.player.frame_step(backward=True)
    assert "not supported" in status_text(window)


def test_snapshot_saves_png(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BABARIFY_SNAPSHOT_DIR", str(tmp_path / "shots"))
    engine = play(qtbot, window, "mock://My: film?duration=600000")
    engine.advance(83_000)
    window.show_page(window.player)
    window.snapshot_action.trigger()
    files = list((tmp_path / "shots").glob("*.png"))
    assert len(files) == 1 and files[0].read_bytes().startswith(b"\x89PNG")
    assert files[0].name == "snapshot 01-23.png"
    window.snapshot_action.trigger()
    assert len(list((tmp_path / "shots").glob("*.png"))) == 2  # never overwritten
    assert status_text(window).startswith("Snapshot saved: ")


def test_many_adjustments_leave_playback_intact(qtbot: QtBot, window: MainWindow) -> None:
    engine = play(qtbot, window)
    engine.advance(5_000)
    panel = window.show_enhancements()
    for i in range(60):
        panel.picture_sliders["brightness"].setValue(50 + i)
        panel.picture_sliders["saturation"].setValue(300 - i * 3)
        panel.aspect.setCurrentIndex(i % panel.aspect.count())
        panel.eq_enabled.setChecked(i % 2 == 0)
        panel.eq_sliders[i % 10].setValue(i % 20 - 10)
    status = window.controller.status()
    assert status.state is S.PLAYING and status.position_ms == 5_000
    assert window.player.message[0] != "Could not open this file"


def test_shortcuts_documented(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, text: shown.append(text))
    window._show_shortcuts()
    assert "Picture &amp; Sound" in shown[0] and "A-B repeat" in shown[0]


def test_engine_options_carry_rotation(qtbot: QtBot, tmp_path: Path) -> None:
    created: list[EngineOptions] = []

    class Recording(LibVlcLikeEngine):
        def __init__(self, options: EngineOptions | None = None) -> None:
            super().__init__(options)
            created.append(self.options)

    win = make_window(qtbot, tmp_path, Recording)
    play(qtbot, win)
    win.player.set_transform(VideoTransform.FLIP_HORIZONTAL)
    qtbot.waitUntil(lambda: len(created) == 2 and win.player.engine_is_ready, timeout=5000)
    assert created[-1].video_transform is VideoTransform.FLIP_HORIZONTAL
    win.close()
