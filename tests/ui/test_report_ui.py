"""M11: Help → Report a problem prepares text to copy; private details only when the user opts in."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from pytestqt.qtbot import QtBot

import babarify_frame.ui.report as report
from babarify_frame import __version__
from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text(
        f"INFO opened {Path.home()}\\Videos\\Secret holiday.mp4\nINFO last line\n", encoding="utf-8"
    )
    monkeypatch.setenv("BABARIFY_LOG_DIR", str(logs))
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    win = MainWindow(factory, load_icon(), engine_name="mock", store=PreferencesStore(tmp_path / "s.json"))
    qtbot.addWidget(win)
    win.show()
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=5000)
    yield win
    win.close()


def test_report_contains_versions_but_no_private_details_by_default(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = Path.home() / "Videos" / "Secret holiday.mp4"
    window.player.controller.open("mock://x?duration=60000")
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    window.player._media_name = media.name
    dialog = window.show_report()
    text = dialog.text.toPlainText()
    assert f"Babarify Media Player {__version__}" in text and "Windows:" in text
    assert "Media video: h264 1920x1080" in text and "engine: mock" in text
    assert "Secret holiday" not in text and "Recent log" not in text
    dialog.include_name.setChecked(True)
    dialog.include_log.setChecked(True)
    text = dialog.text.toPlainText()
    assert "Media name: Secret holiday.mp4" in text and "Recent log (2 lines)" in text
    assert str(Path.home()) not in text and "%USERPROFILE%\\Videos\\Secret holiday.mp4" in text
    dialog.copy_button.click()
    assert QGuiApplication.clipboard().text() == text and dialog.copy_button.text() == "Copied"
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(QUrl(url).toString()) or True)
    dialog.issue_button.click()
    assert opened == [report.ISSUES_URL]
    dialog.close()


def test_report_without_media_or_engine_details() -> None:
    text = report.report_text({"Engine": "not started"}, None, "", "", False, False, [])
    assert "Media: nothing open" in text and "Last error: none" in text
