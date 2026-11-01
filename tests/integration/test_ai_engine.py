"""M9 with the real speech engine: the worker process on locally synthesised speech.

Needs faster-whisper, the tiny model in ``.models/`` (or BABARIFY_MODELS_DIR) and the Windows
speech synthesiser; skipped otherwise. Speech is made on this PC (System.Speech), so nothing is
downloaded. Measured best case: clean synthetic speech; real recordings are harder.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import re
import subprocess
import sys
import time
import wave
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

import babarify_frame.ai.models as ai_models
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory

pytestmark = [pytest.mark.integration, pytest.mark.ui]
ROOT = Path(__file__).resolve().parents[2]
MODELS = Path(os.environ.get("BABARIFY_MODELS_DIR") or ROOT / ".models")
GENERATED = ROOT / "tests" / "fixtures" / "media" / "generated"
TEXT = (
    "The harbour lights came on one by one as the fishing boats returned. "
    "Maria counted seven boats, then eight, and waited for her brother. "
    "The wind had turned cold, and the market stalls were closing early."
)
LEAD_IN_S = 3.0


def _ready() -> str:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return "faster-whisper is not installed"
    os.environ["BABARIFY_MODELS_DIR"] = str(MODELS)
    if ai_models.status("tiny") is not ai_models.ModelStatus.INSTALLED:
        return f"tiny speech model not found in {MODELS}"
    if not default_factory().probe("libvlc").available:
        return "libVLC unavailable"
    return ""


_reason = _ready()
requires_ai = pytest.mark.skipif(bool(_reason), reason=_reason or "ready")


@pytest.fixture(scope="module")
def speech(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("m9-speech")
    raw = folder / "raw.wav"
    script = (
        "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{raw}'); $s.Speak('{TEXT}'); $s.Dispose()"
    )
    done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
    if done.returncode != 0 or not raw.is_file():
        pytest.skip("Windows speech synthesis is not available")
    out = folder / "speech.wav"
    with wave.open(str(raw)) as src, wave.open(str(out), "wb") as dst:
        dst.setparams(src.getparams())
        silence = b"\x00" * int(LEAD_IN_S * src.getframerate()) * src.getsampwidth() * src.getnchannels()
        dst.writeframes(silence + src.readframes(src.getnframes()))
    return out


def run_worker(media: Path, out: Path, model: str = "tiny") -> tuple[list[dict[str, object]], int, list[int]]:
    cmd = [
        sys.executable, "-m", "babarify_frame.ai.worker", "--media", str(media),
        "--model-dir", str(MODELS / f"faster-whisper-{model}"), "--srt", str(out / "s.srt"),
        "--cues", str(out / "c.json"),
    ]  # fmt: skip
    import psutil

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    priorities: list[int] = []
    time.sleep(0.5)
    with contextlib.suppress(psutil.Error):
        # A venv's python.exe is a launcher that runs the real interpreter as its child.
        launcher = psutil.Process(process.pid)
        worker = (launcher.children(recursive=True) or [launcher])[-1]
        priorities.append(worker.nice())
    stdout, _ = process.communicate(timeout=300)
    messages = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    return messages, process.returncode, priorities


def words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower().replace("harbor", "harbour"))


def word_error_rate(reference: str, hypothesis: str) -> float:
    r, h = words(reference), words(hypothesis)
    row = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, row[0] = row[0], i
        for j in range(1, len(h) + 1):
            cur = row[j]
            row[j] = min(row[j] + 1, row[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return row[len(h)] / len(r)


@requires_ai
def test_worker_turns_speech_into_timed_subtitles(speech: Path, tmp_path: Path) -> None:
    import psutil

    messages, code, priorities = run_worker(speech, tmp_path)
    assert code == 0, messages
    done = next(m["done"] for m in messages if "done" in m)
    assert isinstance(done, dict) and done["language"] == "en"
    cues = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    text = " ".join(c[2] for c in cues)
    assert word_error_rate(TEXT, text) <= 0.10, text
    assert LEAD_IN_S - 0.6 <= cues[0][0] / 1000 <= LEAD_IN_S + 0.6  # speech starts after the lead-in
    assert all(a[1] <= b[0] for a, b in itertools.pairwise(cues))
    srt = (tmp_path / "s.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:0") and srt.count(" --> ") == len(cues)
    assert any("progress" in m for m in messages)
    assert priorities == [psutil.BELOW_NORMAL_PRIORITY_CLASS]  # runs behind playback


@requires_ai
@pytest.mark.parametrize("name", ["s_sidecar_720p.mp4", "not_media.mp4"])
def test_worker_explains_files_without_audio(tmp_path: Path, name: str) -> None:
    media = GENERATED / name
    if not media.exists():
        pytest.skip("generated media missing")
    messages, code, _ = run_worker(media, tmp_path)
    assert code == 1
    errors = [m["error"] for m in messages if "error" in m]
    assert errors and "no audio" in str(errors[0])
    assert not (tmp_path / "s.srt").exists()


@requires_ai
def test_silent_audio_gives_no_lines(tmp_path: Path) -> None:
    media = GENERATED / "s_black_720p.mp4"  # an audio track with silence only
    if not media.exists():
        pytest.skip("generated media missing")
    messages, code, _ = run_worker(media, tmp_path)
    assert code == 0
    assert next(m["done"] for m in messages if "done" in m)["cues"] == 0  # type: ignore[index]


@pytest.fixture
def playing(qtbot: QtBot) -> Iterator[object]:
    window = QWidget()
    window.resize(480, 270)
    window.show()
    engine = default_factory().create("libvlc")
    engine.set_video_output(int(window.winId()))
    yield engine
    engine.close()
    window.close()
    window.deleteLater()


@requires_ai
def test_playback_keeps_going_while_transcribing(
    qtbot: QtBot, playing: object, speech: Path, tmp_path: Path
) -> None:
    from babarify_frame.playback.contracts import PlaybackEngine

    engine = playing
    assert isinstance(engine, PlaybackEngine)
    film = GENERATED / "h264_1080p30_aac.mp4"
    if not film.exists():
        pytest.skip("generated media missing")
    engine.open_media(str(film))
    qtbot.waitUntil(lambda: engine.get_playback_state().position_ms > 500, timeout=15_000)
    cmd = [
        sys.executable, "-m", "babarify_frame.ai.worker", "--media", str(speech),
        "--model-dir", str(MODELS / "faster-whisper-tiny"), "--srt", str(tmp_path / "s.srt"),
        "--cues", str(tmp_path / "c.json"),
    ]  # fmt: skip
    worker = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        start_pos = engine.get_playback_state().position_ms
        start_dropped = engine.playback_stats().get("dropped", 0)
        started = time.monotonic()
        qtbot.wait(4000)
        advanced = engine.get_playback_state().position_ms - start_pos
        elapsed = (time.monotonic() - started) * 1000
        dropped = engine.playback_stats().get("dropped", 0) - start_dropped
    finally:
        worker.wait(timeout=300)
    assert engine.get_playback_state().state is S.PLAYING
    assert advanced >= 0.9 * elapsed, (advanced, elapsed)
    assert dropped <= 10, dropped
