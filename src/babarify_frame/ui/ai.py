"""Local AI UI (M9): subtitle generation job and dialog, spoken-word search, model download.

The job starts ``babarify_frame.ai.worker`` as its own process and reads its JSON lines on a
thread; Cancel ends the process. Nothing here imports the speech engine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import typing
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame.ai import models
from babarify_frame.ai.subtitles import MACHINE_TAG, subtitle_path
from babarify_frame.library.models import SpokenHit, Transcript
from babarify_frame.ui.bridge import UiBridge
from babarify_frame.ui.widgets import format_time, plain_text

LOCAL_NOTE = (
    "Runs on this PC with an open-source speech model. The video, its sound and the subtitles "
    "are not uploaded anywhere. The result is machine-generated and can contain mistakes."
)


@dataclass(frozen=True)
class JobResult:
    srt: Path
    cues: list[tuple[int, int, str]]
    language: str
    model: str


def worker_executable() -> Path | None:
    """The release's worker (optional installer component, M10); None when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "ai" / "babarify-ai-worker.exe"
    return None


def ai_installed() -> bool:
    executable = worker_executable()
    return executable is None or executable.is_file()


def worker_command(media: str, model: str, language: str, srt: Path, cues: Path) -> list[str]:
    executable = worker_executable()
    if executable is not None:
        start = [str(executable)]
    else:
        start = [sys.executable, "-m", "babarify_frame.ai.worker"]
    return [
        *start,
        "--media", media, "--model-dir", str(models.model_path(model)),
        "--language", language or "auto", "--srt", str(srt), "--cues", str(cues),
    ]  # fmt: skip


class SubtitleJob(QObject):
    """One transcription at a time. Signals arrive on the UI thread."""

    stage = Signal(str)
    progress = Signal(float)  # 0..1
    finished = Signal(object, str)  # JobResult | None, error ("" on success, "cancelled")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bridge = UiBridge(self)
        self._bridge.delivered.connect(self._deliver)
        self._process: subprocess.Popen[str] | None = None
        self._cancelled = False

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self, media: str, model: str, language: str) -> None:
        if self._process is not None:
            raise RuntimeError("a subtitle job is already running")
        srt = subtitle_path(media, language or "und")
        cues = srt.with_suffix(".cues.json")
        srt.parent.mkdir(parents=True, exist_ok=True)
        self._cancelled = False
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._process = subprocess.Popen(
            worker_command(media, model, language, srt, cues),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=flags,
        )
        process = self._process
        threading.Thread(target=self._read, args=(process, media, srt, cues, model), daemon=True).start()

    def cancel(self) -> None:
        self._cancelled = True
        if self._process is not None:
            self._process.kill()

    def _read(self, process: subprocess.Popen[str], media: str, srt: Path, cues: Path, model: str) -> None:
        error, done = "", None
        assert process.stdout is not None
        for line in process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if "stage" in message:
                self._bridge.post(("stage", message["stage"]))
            elif "progress" in message:
                self._bridge.post(("progress", float(message["progress"])))
            elif "error" in message:
                error = str(message["error"])
            elif "done" in message:
                done = message["done"]
        process.wait()
        result = None
        if done is not None and not self._cancelled:
            try:
                rows = json.loads(cues.read_text(encoding="utf-8"))
                # With automatic detection the language is known only now: name the file after it.
                named = subtitle_path(media, str(done["language"]))
                if named != srt:
                    srt = srt.replace(named)
                result = JobResult(
                    srt, [(int(a), int(b), str(t)) for a, b, t in rows], done["language"], model
                )
            except (OSError, ValueError, KeyError) as exc:
                error = f"could not read the result: {exc}"
            finally:
                cues.unlink(missing_ok=True)
        if result is None:
            srt.unlink(missing_ok=True)
            cues.unlink(missing_ok=True)
            error = (
                "cancelled"
                if self._cancelled
                else (error or f"the worker stopped (code {process.returncode})")
            )
        self._bridge.post(("finished", result, error))

    def _deliver(self, payload: object) -> None:
        kind, *rest = typing.cast(tuple[Any, ...], payload)
        if kind == "stage":
            self.stage.emit(rest[0])
        elif kind == "progress":
            self.progress.emit(rest[0])
        else:
            self._process = None
            self.finished.emit(rest[0], rest[1])


class GenerateSubtitlesDialog(QDialog):
    """Choose language and model, then follow progress. ``start_requested`` and ``cancel_requested``
    go to the window, which owns the job."""

    start_requested = Signal(str, str)  # model, language
    cancel_requested = Signal()
    load_existing_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generate subtitles (local)")
        self.setMinimumWidth(520)
        box = QVBoxLayout(self)
        self.media = QLabel()
        self.media.setObjectName("subtitle")
        self.media.setWordWrap(True)
        box.addWidget(self.media)
        form = QFormLayout()
        self.language = QComboBox()
        self.language.setAccessibleName("Spoken language")
        for code, name in models.SPEECH_LANGUAGES.items():
            self.language.addItem(name, code)
        self.model = QComboBox()
        self.model.setAccessibleName("Speech model")
        self.model.currentIndexChanged.connect(lambda _index: self._update_estimate())
        form.addRow("Spoken language", self.language)
        form.addRow("Speech model", self.model)
        box.addLayout(form)
        self.estimate = QLabel()
        self.estimate.setObjectName("muted")
        self.estimate.setWordWrap(True)
        box.addWidget(self.estimate)
        self.existing = QLabel()
        self.existing.setWordWrap(True)
        self.load_button = QPushButton("Load these subtitles")
        self.load_button.clicked.connect(self.load_existing_requested)
        box.addWidget(self.existing)
        box.addWidget(self.load_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)
        plain_text(self.media, self.status, self.existing)
        box.addWidget(self.bar)
        box.addWidget(self.status)
        note = QLabel(LOCAL_NOTE)
        note.setObjectName("caption")
        note.setWordWrap(True)
        box.addWidget(note)
        self.buttons = QDialogButtonBox()
        self.start_button = self.buttons.addButton("Generate", QDialogButtonBox.ButtonRole.AcceptRole)
        self.settings_button = self.buttons.addButton(
            "Get a speech model…", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.cancel_button = self.buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self.start_button.clicked.connect(self._start)
        self.settings_button.clicked.connect(self.settings_requested)
        self.cancel_button.clicked.connect(self._cancel)
        box.addWidget(self.buttons)
        self._running = False
        self._duration_ms: int | None = None

    def prepare(
        self,
        media_name: str,
        duration_ms: int | None,
        installed: list[str],
        preferred_model: str,
        language: str,
        existing: Transcript | None,
    ) -> None:
        self.media.setText(media_name)
        self._duration_ms = duration_ms
        self.model.clear()
        for name in installed:
            self.model.addItem(models.MODELS[name].label, name)
        if preferred_model in installed:
            self.model.setCurrentIndex(installed.index(preferred_model))
        self.language.setCurrentIndex(max(0, self.language.findData(language)))
        if existing is not None:
            lang = models.SPEECH_LANGUAGES.get(existing.language, existing.language)
            self.existing.setText(
                f"Subtitles were already generated for this file ({lang}, {existing.model} model, "
                f"{existing.cue_count} lines). Generating again replaces them."
            )
        self.existing.setVisible(existing is not None)
        self.load_button.setVisible(existing is not None)
        self.settings_button.setVisible(not installed)
        self._update_estimate()
        self.set_running(False)
        self.bar.setValue(0)
        self.status.setText(
            "" if installed else "No speech model is installed yet. Download one in Settings → AI features."
        )

    def _update_estimate(self) -> None:
        name = self.model.currentData()
        if name is None:
            self.estimate.setText("")
            return
        speed = models.MODELS[str(name)].speed_x  # measured end to end (tools/ai_measure.py)
        if self._duration_ms:
            seconds = self._duration_ms / 1000 / speed
            length = "less than a minute" if seconds < 60 else f"about {round(seconds / 60)} min"
            self.estimate.setText(
                f"Takes {length} on the M9 test PC (plus a moment to read the sound). "
                "You can keep watching meanwhile."
            )
        else:
            self.estimate.setText("")

    def set_running(self, running: bool) -> None:
        self._running = running
        self.start_button.setEnabled(not running and self.model.count() > 0)
        self.language.setEnabled(not running)
        self.model.setEnabled(not running)
        self.load_button.setEnabled(not running)
        self.bar.setVisible(running or self.bar.value() > 0)
        self.cancel_button.setText("Stop" if running else "Close")

    def show_stage(self, stage: str) -> None:
        self.status.setText(
            {"audio": "Reading the sound…", "speech": "Recognising speech…"}.get(stage, stage)
        )

    def show_progress(self, fraction: float) -> None:
        self.bar.setValue(round(max(0.0, min(1.0, fraction)) * 1000))

    def show_result(self, text: str) -> None:
        self.status.setText(text)
        self.set_running(False)

    def _start(self) -> None:
        if self.model.currentData() is None:
            return
        self.set_running(True)
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self.status.setText("Starting…")
        self.start_requested.emit(str(self.model.currentData()), str(self.language.currentData()))

    def _cancel(self) -> None:
        if self._running:
            self.cancel_requested.emit()
        else:
            self.close()


class SpokenSearchDialog(QDialog):
    """Search the text of machine-generated subtitles; open a result at its time."""

    open_requested = Signal(str, int)  # path, position ms

    def __init__(self, search: Callable[[str], list[SpokenHit]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Search spoken words")
        self.resize(620, 460)
        self._search = search
        box = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Words someone says, e.g. harbour lights")
        self.query.setAccessibleName("Spoken words")
        self.query.textChanged.connect(self._run)
        box.addWidget(self.query)
        self.results = QListWidget()
        self.results.setAccessibleName("Results")
        self.results.itemActivated.connect(self._open)
        box.addWidget(self.results, stretch=1)
        self.note = QLabel()
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        box.addWidget(self.note)
        self._hits: list[SpokenHit] = []
        self._run("")

    def _run(self, text: str) -> None:
        self._hits = self._search(text) if text.strip() else []
        self.results.clear()
        for hit in self._hits:
            item = QListWidgetItem(f"{hit.title}  ·  {format_time(hit.start_ms)}\n{hit.text}")
            self.results.addItem(item)
        if not text.strip():
            self.note.setText(
                "Searches the machine-generated subtitles made on this PC (Audio & Subtitles → "
                "Generate subtitles). Double-click a result to play from there."
            )
        else:
            self.note.setText(f"{len(self._hits)} result{'s' if len(self._hits) != 1 else ''}")

    def _open(self, item: QListWidgetItem) -> None:
        row = self.results.row(item)
        if 0 <= row < len(self._hits):
            hit = self._hits[row]
            self.open_requested.emit(hit.path, hit.start_ms)


class ModelDownload(QObject):
    """Download a model on a thread (after the user agreed); ``finished(name, error)``."""

    message = Signal(str)
    finished = Signal(str, str)

    def __init__(self, parent: QObject | None = None, fetch: models.Fetch | None = None) -> None:
        super().__init__(parent)
        self._bridge = UiBridge(self)
        self._bridge.delivered.connect(self._deliver)
        self._cancel = threading.Event()
        self._fetch = fetch
        self.running = False

    def start(self, name: str) -> None:
        self.running = True
        self._cancel.clear()

        def work() -> None:
            try:
                kwargs = {"fetch": self._fetch} if self._fetch is not None else {}
                models.download(
                    name, lambda text: self._bridge.post(("message", text)), self._cancel, **kwargs
                )
                self._bridge.post(("finished", name, ""))
            except models.ModelError as exc:
                self._bridge.post(("finished", name, str(exc)))

        threading.Thread(target=work, name="model-download", daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()

    def _deliver(self, payload: object) -> None:
        kind, *rest = typing.cast(tuple[Any, ...], payload)
        if kind == "message":
            self.message.emit(rest[0])
        else:
            self.running = False
            self.finished.emit(rest[0], rest[1])


def generated_size(transcripts: list[Transcript]) -> int:
    return sum(os.path.getsize(t.srt_path) for t in transcripts if os.path.isfile(t.srt_path))


def is_machine_subtitle(path: str) -> bool:
    return f".{MACHINE_TAG}." in Path(path).name
