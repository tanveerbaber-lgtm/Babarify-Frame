"""M7 real-engine checks on libVLC: each control changes the picture on screen (screen pixels).

The window stays on top and is checked to own its screen area (R16) before each measurement,
because the video is drawn by Direct3D and can only be read back from the screen. Colour bars
(h264_1080p30_aac.mp4) make the effects measurable: the second bar from the left is pure green.
"""

from __future__ import annotations

import ctypes
import time
from collections.abc import Iterator
from ctypes import wintypes
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from babarify_frame.core.enhancements import EqualizerSettings, PictureSettings, VideoTransform
from babarify_frame.core.events import ErrorOccurred, PlaybackEvent
from babarify_frame.core.models import EngineOptions
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.integration, pytest.mark.ui]

MEDIA = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "media" / "generated"
BARS = MEDIA / "h264_1080p30_aac.mp4"
_probe = default_factory().probe("libvlc")
requires_libvlc = pytest.mark.skipif(not _probe.available, reason=f"libvlc unavailable: {_probe.detail}")


def pump(seconds: float) -> None:
    app = QApplication.instance()
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        assert app is not None
        app.processEvents()
        time.sleep(0.01)


def owns_screen(widget: QWidget) -> bool:
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = wintypes.HWND
    ratio = widget.devicePixelRatio()
    top_left = widget.mapToGlobal(widget.rect().topLeft())
    own = int(widget.window().winId())
    for fx in (0.1, 0.5, 0.9):
        for fy in (0.1, 0.5, 0.9):
            x = int((top_left.x() + widget.width() * fx) * ratio)
            y = int((top_left.y() + widget.height() * fy) * ratio)
            hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
            root = user32.GetAncestor(hwnd, 2) if hwnd else None
            if not root or int(root) != own:
                return False
    return True


class Screen:
    def __init__(self, host: QWidget) -> None:
        self.host = host

    def grab(self) -> QImage:
        pump(0.5)
        self.host.raise_()
        if not owns_screen(self.host):
            pytest.fail("another window covers the test video window; measurement would be invalid")
        top_left = self.host.mapToGlobal(self.host.rect().topLeft())
        return (
            self.host.screen()
            .grabWindow(0, top_left.x(), top_left.y(), self.host.width(), self.host.height())
            .toImage()
        )

    def green_bar(self) -> QColor:
        """Median colour of 15 points down the green bar: the moving test line and the timecode
        cross single pixels, so one sample can land on them."""
        img = self.grab()
        x = int(img.width() * 0.22)
        points = [QColor(img.pixel(x, int(img.height() * f / 20))) for f in range(3, 18)]

        def median(values: list[int]) -> int:
            return sorted(values)[len(values) // 2]

        return QColor(
            median([c.red() for c in points]),
            median([c.green() for c in points]),
            median([c.blue() for c in points]),
        )

    def wait_for_picture(self, timeout: float = 8.0) -> None:
        """Wait while playing until the window shows a picture, not the black start-up frame."""
        deadline = time.perf_counter() + timeout
        while self.black_columns() > 0.9 and time.perf_counter() < deadline:
            pass

    def black_columns(self) -> float:
        """Fraction of columns that are black from top to bottom (pillarbox)."""
        img = self.grab()
        cols = [
            x
            for x in range(0, img.width(), 4)
            if all(QColor(img.pixel(x, y)).lightness() < 12 for y in range(0, img.height(), 16))
        ]
        return len(cols) * 4 / img.width()


@pytest.fixture
def host(qtbot: QtBot) -> Iterator[QWidget]:
    if not BARS.exists():
        pytest.skip("generated media missing")
    widget = QWidget()
    widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    widget.resize(640, 360)
    widget.move(60, 60)
    widget.show()
    yield widget
    widget.close()
    widget.deleteLater()


def start(host: QWidget, hardware: bool, transform: VideoTransform = VideoTransform.NONE):  # type: ignore[no-untyped-def]
    engine = default_factory().create(
        "libvlc", EngineOptions(hardware_decoding=hardware, video_transform=transform)
    )
    errors: list[PlaybackEvent] = []
    engine.subscribe(lambda e: errors.append(e) if isinstance(e, ErrorOccurred) else None)
    engine.set_video_output(int(host.winId()))
    engine.open_media(str(BARS))
    deadline = time.perf_counter() + 15
    while engine.get_playback_state().state is not S.PLAYING and time.perf_counter() < deadline:
        pump(0.05)
    pump(1.0)
    return engine, errors


def settle(engine) -> None:  # type: ignore[no-untyped-def]
    """Let a few new frames through so the change is on screen, then hold still."""
    engine.play()
    pump(0.3)
    engine.pause()


@requires_libvlc
@pytest.mark.parametrize("hardware", [True, False], ids=["hardware", "software"])
def test_picture_adjustments_change_the_picture(host: QWidget, hardware: bool) -> None:
    engine, errors = start(host, hardware)
    screen = Screen(host)
    try:
        screen.wait_for_picture()
        engine.pause()
        base = screen.green_bar()
        assert base.green() > 180 and base.red() < 40  # pure green bar
        caps = engine.get_capabilities()
        assert ("gamma" in caps.picture_adjustments) is (not hardware)

        engine.set_picture(PictureSettings(brightness=1.5))
        settle(engine)
        assert screen.green_bar().lightness() > base.lightness() + 15
        engine.set_picture(PictureSettings(saturation=0.0))  # changed while the filter is on (R30)
        settle(engine)
        grey = screen.green_bar()
        assert grey.hsvSaturation() < 20
        engine.set_picture(PictureSettings(hue=120.0))
        settle(engine)
        assert screen.green_bar().red() > 150  # green turned towards red
        engine.set_picture(PictureSettings(contrast=0.3))
        settle(engine)
        assert abs(screen.green_bar().green() - base.green()) > 10
        if not hardware:
            engine.set_picture(PictureSettings(gamma=2.0))
            settle(engine)
            assert screen.green_bar().lightness() > base.lightness() + 10
        engine.set_picture(PictureSettings())  # back to normal
        settle(engine)
        restored = screen.green_bar()
        assert abs(restored.green() - base.green()) <= 6 and restored.red() < 40
        assert not errors
    finally:
        engine.close()


@requires_libvlc
def test_aspect_crop_and_zoom(host: QWidget) -> None:
    engine, errors = start(host, hardware=True)
    screen = Screen(host)
    try:
        engine.pause()
        assert screen.black_columns() < 0.02
        engine.set_video_geometry("4:3", "", 0.0)
        settle(engine)
        assert 0.15 < screen.black_columns() < 0.35  # pillarbox: 16:9 window, 4:3 picture
        engine.set_video_geometry("", "4:3", 0.0)
        settle(engine)
        assert 0.15 < screen.black_columns() < 0.35  # cropped to 4:3, fitted
        engine.set_video_geometry("", "", 0.5)
        settle(engine)
        assert screen.black_columns() > 0.0  # a 50 % picture does not fill the window (or overflows)
        engine.set_video_geometry("", "", 0.0)
        settle(engine)
        assert screen.black_columns() < 0.02
        assert not errors
    finally:
        engine.close()


@requires_libvlc
@pytest.mark.parametrize("hardware", [True, False], ids=["hardware", "software"])
def test_rotation_turns_the_bars(host: QWidget, hardware: bool) -> None:
    engine, errors = start(host, hardware, VideoTransform.ROTATE_90)
    screen = Screen(host)
    try:
        engine.pause()
        img = screen.grab()
        w, h = img.width(), img.height()
        down = {QColor(img.pixel(w // 2, y)).name() for y in range(h // 20, h, h // 10)}
        across = {QColor(img.pixel(x, h // 2)).name() for x in range(int(w * 0.4), int(w * 0.6), w // 50)}
        assert len(down) >= 5  # the colour bars now run top to bottom
        assert len(across) <= 2
        assert engine.get_capabilities().rotation == "restart"
        assert not errors
    finally:
        engine.close()


@requires_libvlc
def test_frame_step_and_snapshot(host: QWidget, tmp_path: Path) -> None:
    engine, errors = start(host, hardware=True)
    screen = Screen(host)
    try:
        engine.pause()
        before = screen.grab()
        for _ in range(5):
            engine.frame_step()
            pump(0.15)
        after = screen.grab()
        changed = sum(
            1
            for y in range(0, before.height(), 6)
            for x in range(0, before.width(), 6)
            if before.pixel(x, y) != after.pixel(x, y)
        )
        assert changed > 100  # the moving line and timecode advanced
        assert engine.get_playback_state().state is S.PAUSED
        target = tmp_path / "frame.png"
        engine.take_snapshot(str(target))
        deadline = time.perf_counter() + 5
        while not target.exists() and time.perf_counter() < deadline:
            pump(0.05)
        image = QImage(str(target))
        assert (image.width(), image.height()) == (1920, 1080)
        assert not errors
    finally:
        engine.close()


@requires_libvlc
def test_equalizer_presets_come_from_the_engine(host: QWidget) -> None:
    engine, errors = start(host, hardware=True)
    try:
        caps = engine.get_capabilities()
        assert len(caps.equalizer_presets) == 18 and "Rock" in caps.equalizer_presets
        assert caps.equalizer_bands_hz == (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
        rock = engine.equalizer_preset("Rock")
        assert rock.enabled and rock.preset == "Rock" and any(b != 0 for b in rock.bands_db)
        engine.set_equalizer(rock)
        engine.set_equalizer(EqualizerSettings())
        assert engine.get_playback_state().state is S.PLAYING
        assert not errors
    finally:
        engine.close()


@requires_libvlc
def test_many_adjustments_do_not_disturb_playback(host: QWidget) -> None:
    engine, errors = start(host, hardware=True)
    try:
        start_ms = engine.get_playback_state().position_ms
        for i in range(120):
            engine.set_picture(PictureSettings(brightness=0.5 + (i % 10) / 10, hue=float(i % 360 - 180)))
            engine.set_video_geometry(("", "16:9", "4:3")[i % 3], "", (0.0, 1.0)[i % 2])
            engine.set_equalizer(EqualizerSettings(i % 2 == 0, "", 0.0, (float(i % 20 - 10),) * 10))
            pump(0.01)
        pump(1.0)
        status = engine.get_playback_state()
        assert status.state is S.PLAYING
        assert status.position_ms > start_ms + 1_000
        assert not errors
    finally:
        engine.close()
