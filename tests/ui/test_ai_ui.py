"""M9 UI: AI switch, model download and deletion, subtitle generation job, spoken-word search.

The worker is replaced by ``tests/fake_ai_worker.py`` (same arguments and protocol), so the real
job runner, process handling and cancel are exercised without a speech model.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

import babarify_frame.ai.models as ai_models
import babarify_frame.ui.ai as ui_ai
from babarify_frame.ai.models import ModelFile, ModelStatus, SpeechModel
from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine
from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow

pytestmark = pytest.mark.ui
FAKE_WORKER = Path(__file__).resolve().parents[1] / "fake_ai_worker.py"
CONTENT = {"config.json": b"{}", "model.bin": b"weights" * 100}
FILES = tuple(ModelFile(n, len(b), hashlib.sha256(b).hexdigest()) for n, b in CONTENT.items())


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BABARIFY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("BABARIFY_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setitem(
        ai_models.MODELS, "tiny", SpeechModel("tiny", "Tiny", "x/tiny", "r" * 40, FILES, 10.0)
    )
    monkeypatch.setitem(ai_models.MODELS, "base", SpeechModel("base", "Base", "x/base", "r" * 40, FILES, 6.0))

    def fake_command(media: str, model: str, language: str, srt: Path, cues: Path) -> list[str]:
        return [sys.executable, str(FAKE_WORKER), "--media", media, "--model-dir", model,
                "--language", language or "auto", "--srt", str(srt), "--cues", str(cues)]  # fmt: skip

    monkeypatch.setattr(ui_ai, "worker_command", fake_command)


def install(name: str) -> None:
    folder = ai_models.model_path(name)
    folder.mkdir(parents=True, exist_ok=True)
    for file_name, data in CONTENT.items():
        (folder / file_name).write_bytes(data)


def make_window(qtbot: QtBot, tmp_path: Path, ai: bool = True) -> MainWindow:
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    store = PreferencesStore(tmp_path / "settings.json")
    store.save(Preferences(ai_enabled=ai))
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
    if win.subtitle_job.running:
        win.subtitle_job.cancel()
    win.close()


def play_file(qtbot: QtBot, window: MainWindow, tmp_path: Path, name: str = "film.mp4") -> str:
    media = tmp_path / name
    media.write_bytes(b"\x00")
    window.open_path(str(media))
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    return str(media)


def test_ai_is_off_until_switched_on(qtbot: QtBot, tmp_path: Path) -> None:
    win = make_window(qtbot, tmp_path, ai=False)
    play_file(qtbot, win, tmp_path)
    assert not win.generate_subtitles_action.isVisible() and not win.spoken_search_action.isVisible()
    assert win.show_generate_subtitles() is None and win.show_spoken_search() is None
    win.show_page(win.settings)
    win.settings.ai_enabled.setChecked(True)
    assert win.generate_subtitles_action.isEnabled() and win.spoken_search_action.isEnabled()
    assert PreferencesStore(tmp_path / "settings.json").load().ai_enabled
    win.close()


def test_generate_needs_a_model_and_points_to_settings(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    play_file(qtbot, window, tmp_path)
    dialog = window.show_generate_subtitles()
    assert dialog is not None and not dialog.start_button.isEnabled()
    assert "No speech model is installed" in dialog.status.text() and dialog.settings_button.isVisible()
    dialog.settings_button.click()
    assert window.current_page() is window.settings


def test_generating_subtitles_adds_a_machine_track_and_indexes_it(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    install("base")
    media = play_file(qtbot, window, tmp_path)
    dialog = window.show_generate_subtitles()
    assert dialog is not None and dialog.start_button.isEnabled()
    assert ui_ai.LOCAL_NOTE in [label.text() for label in dialog.findChildren(type(dialog.status))]
    dialog.start_button.click()
    qtbot.waitUntil(lambda: "Done: 3 lines in English" in dialog.status.text(), timeout=15_000)
    assert dialog.bar.value() == 1000 and "machine-generated" in dialog.status.text()
    engine = window.player.controller.engine
    assert isinstance(engine, MockEngine)
    added = [c for c in engine.calls if c.startswith("add_subtitle:")]
    assert added and added[0].endswith(".en.machine-generated.srt")
    srt = Path(added[0].split(":", 1)[1])
    assert srt.is_relative_to(tmp_path / "cfg") and srt.is_file()
    transcript = window.library_service.db.transcript_for(media)
    assert transcript is not None and transcript.cue_count == 3 and transcript.model == "base"
    # Opening the dialog again offers the existing subtitles.
    window._generate_dialog.close()  # type: ignore[union-attr]
    dialog = window.show_generate_subtitles()
    assert dialog is not None and dialog.load_button.isVisible() and "3 lines" in dialog.existing.text()


def test_spoken_search_opens_the_file_at_the_words(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    window.library_service.db.save_transcript(
        str(tmp_path / "film.mp4"), "film.mp4", "x.srt", "en", "base", [(42_000, "The wind had turned cold")]
    )
    (tmp_path / "film.mp4").write_bytes(b"\x00")
    dialog = window.show_spoken_search()
    assert dialog is not None
    dialog.query.setText("turned co")
    assert dialog.results.count() == 1 and "00:42" in dialog.results.item(0).text()
    assert "[turned]" in dialog.results.item(0).text()
    dialog.results.itemActivated.emit(dialog.results.item(0))
    qtbot.waitUntil(lambda: window.player.state is S.PLAYING, timeout=3000)
    qtbot.waitUntil(lambda: window.player.controller.status().position_ms == 41_000, timeout=3000)


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("nospeech.mp4", "No speech was found"),
        ("fail.mp4", "no audio that could be read"),
        ("crash.mp4", "the worker stopped (code 3)"),
    ],
)
def test_job_failures_are_explained_and_leave_nothing_behind(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, name: str, message: str
) -> None:
    install("tiny")
    play_file(qtbot, window, tmp_path, name)
    dialog = window.show_generate_subtitles()
    assert dialog is not None
    dialog.start_button.click()
    qtbot.waitUntil(lambda: message in dialog.status.text(), timeout=15_000)
    assert not window.subtitle_job.running and dialog.start_button.isEnabled()
    assert window.library_service.db.transcripts() == []
    if name != "nospeech.mp4":
        assert not list((tmp_path / "cfg").rglob("*.srt"))


def test_cancel_and_switching_ai_off_stop_the_worker(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    install("tiny")
    play_file(qtbot, window, tmp_path, "slow.mp4")
    dialog = window.show_generate_subtitles()
    assert dialog is not None
    dialog.start_button.click()
    qtbot.waitUntil(lambda: dialog.bar.value() == 100, timeout=15_000)
    assert dialog.cancel_button.text() == "Stop"
    dialog.cancel_button.click()
    qtbot.waitUntil(lambda: dialog.status.text() == "Stopped.", timeout=10_000)
    assert not list((tmp_path / "cfg").rglob("*.srt"))
    dialog.start_button.click()
    qtbot.waitUntil(lambda: window.subtitle_job.running and dialog.bar.value() == 100, timeout=15_000)
    window.show_page(window.settings)
    window.settings.ai_enabled.setChecked(False)
    qtbot.waitUntil(lambda: not window.subtitle_job.running, timeout=10_000)
    assert not window.generate_subtitles_action.isVisible()


def test_model_download_asks_first_then_installs(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fetch(_model: SpeechModel, file: ModelFile, folder: Path) -> None:
        (folder / file.name).write_bytes(CONTENT[file.name])

    real_download = ai_models.download
    monkeypatch.setattr(
        ai_models, "download", lambda name, progress, cancel: real_download(name, progress, cancel, fetch)
    )
    questions: list[str] = []

    def ask(_parent: object, _title: str, text: str, *args: object) -> QMessageBox.StandardButton:
        questions.append(text)
        return QMessageBox.StandardButton.No if len(questions) == 1 else QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", ask)
    window.show_page(window.settings)
    s = window.settings
    s.ai_model.setCurrentIndex(s.ai_model.findData("base"))
    window._refresh_ai_status()
    assert s.ai_model_status.text() == "Not downloaded" and s.ai_download.isEnabled()
    s.ai_download.click()  # declined: nothing happens
    assert ai_models.status("base") is ModelStatus.MISSING and not window.model_download.running
    assert (
        "huggingface.co/x/base" in questions[0] and "nothing about you or your media is sent" in questions[0]
    )
    s.ai_download.click()
    qtbot.waitUntil(lambda: ai_models.status("base") is ModelStatus.INSTALLED, timeout=10_000)
    qtbot.waitUntil(lambda: s.ai_model_status.text() == "Installed", timeout=5_000)
    assert not s.ai_download.isEnabled() and s.ai_delete_model.isEnabled()
    s.ai_delete_model.click()
    assert ai_models.status("base") is ModelStatus.MISSING


def test_generated_subtitles_can_be_deleted(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install("tiny")
    play_file(qtbot, window, tmp_path)
    dialog = window.show_generate_subtitles()
    assert dialog is not None
    dialog.start_button.click()
    qtbot.waitUntil(lambda: "Done" in dialog.status.text(), timeout=15_000)
    window.show_page(window.settings)
    assert window.settings.ai_generated.text().startswith("Generated subtitles: 1 file")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.settings.ai_delete_generated.click()
    assert window.library_service.db.transcripts() == [] and not list((tmp_path / "cfg").rglob("*.srt"))
    assert window.settings.ai_generated.text() == "Generated subtitles: 0 files"
    assert not window.settings.ai_delete_generated.isEnabled()
