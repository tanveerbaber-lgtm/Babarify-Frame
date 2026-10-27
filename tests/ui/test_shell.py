from __future__ import annotations

import subprocess
import sys
import threading

import pytest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from babarify_frame import PRODUCT_NAME, TAGLINE
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


def fake_factory(available: bool) -> EngineFactory:
    factory = EngineFactory()
    for name in ("libvlc", "mpv"):
        factory.register(
            EngineDescriptor(
                name,
                f"{name} (candidate)",
                MockEngine,
                lambda n=name: EngineProbe(
                    n, available, "9.9" if available else None, "" if available else "dll missing"
                ),
            )
        )
    return factory


def test_window_shows_branding(qtbot: QtBot) -> None:
    window = MainWindow(fake_factory(True), load_icon())
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == PRODUCT_NAME
    assert not window.windowIcon().isNull()
    texts = {label.text() for label in window.findChildren(QLabel)}
    assert {PRODUCT_NAME, TAGLINE} <= texts


def test_icon_resources_exist() -> None:
    icon = load_icon()
    assert not icon.isNull()
    assert {s.width() for s in icon.availableSizes()} >= {16, 32, 256}


@pytest.mark.parametrize("available", [True, False])
def test_engine_probes_reported_on_ui_thread(qtbot: QtBot, available: bool) -> None:
    window = MainWindow(fake_factory(available), load_icon())
    qtbot.addWidget(window)
    window.start_engine_probes()
    qtbot.waitUntil(lambda: len(window.probe_results) == 2, timeout=5000)
    text = window._engine_labels["mpv"].text()
    assert ("loaded 9.9" in text) if available else ("unavailable" in text and "dll missing" in text)


def test_open_action_is_disabled_until_m2(qtbot: QtBot) -> None:
    window = MainWindow(fake_factory(True), load_icon())
    qtbot.addWidget(window)
    open_actions = [a for a in window.menuBar().actions()[0].menu().actions() if a.text().startswith("&Open")]
    assert open_actions and not open_actions[0].isEnabled()


def test_bridge_delivers_on_ui_thread(qtbot: QtBot) -> None:
    bridge = UiBridge()
    seen: list[tuple[object, bool]] = []
    main = threading.current_thread()
    bridge.delivered.connect(lambda p: seen.append((p, threading.current_thread() is main)))
    worker = threading.Thread(target=lambda: bridge.post("hello"))
    worker.start()
    worker.join()
    qtbot.waitUntil(lambda: bool(seen), timeout=2000)
    assert seen == [("hello", True)]


def test_app_starts_and_exits_cleanly() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "babarify_frame", "--smoke-test", "800"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "exited cleanly with code 0" in proc.stderr
