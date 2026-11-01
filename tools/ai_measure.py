"""M9 measurements: speech-to-text speed and accuracy, and the effect on playback.

1. For each installed model: the worker process on local synthetic speech (wall time including
   start-up and audio extraction, word error rate, first-cue timing).
2. Playback impact: libVLC plays H.264 1080p for 10 s alone, then while the worker (base)
   transcribes; frames dropped and position advance are compared.
Writes tools/engine-benchmark/results/ai_measure.json (or the path given).
Usage:  python tools/ai_measure.py [out.json]   (BABARIFY_MODELS_DIR, default .models)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_speech import TEXT, make_speech

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("BABARIFY_MODELS_DIR", str(ROOT / ".models"))
from babarify_frame.ai import models  # noqa: E402  (reads BABARIFY_MODELS_DIR)
from babarify_frame.playback.factory import default_factory  # noqa: E402

FILM = ROOT / "tests" / "fixtures" / "media" / "generated" / "h264_1080p30_aac.mp4"


def words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower().replace("harbor", "harbour"))


def wer(reference: str, hypothesis: str) -> float:
    r, h = words(reference), words(hypothesis)
    row = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, row[0] = row[0], i
        for j in range(1, len(h) + 1):
            cur = row[j]
            row[j] = min(row[j] + 1, row[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return row[len(h)] / len(r)


def worker(media: Path, model: str, out: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "babarify_frame.ai.worker", "--media", str(media),
         "--model-dir", str(models.model_path(model)), "--srt", str(out / f"{model}.srt"),
         "--cues", str(out / f"{model}.json")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip


def accuracy(media: Path, work: Path) -> list[dict[str, object]]:
    rows = []
    for model in models.installed_models():
        started = time.perf_counter()
        code = worker(media, model, work).wait(timeout=600)
        seconds = time.perf_counter() - started
        cues = json.loads((work / f"{model}.json").read_text(encoding="utf-8")) if code == 0 else []
        text = " ".join(c[2] for c in cues)
        rows.append({
            "model": model, "exit": code, "wall_s": round(seconds, 1),
            "wer": round(wer(TEXT, text), 3),
            "first_cue_s": round(cues[0][0] / 1000, 2) if cues else None, "cues": len(cues),
        })  # fmt: skip
        print(rows[-1])
    return rows


def playback(app: QApplication, media: Path, work: Path) -> dict[str, object]:
    host = QWidget()
    host.resize(960, 540)
    host.show()
    engine = default_factory().create("libvlc")
    engine.set_video_output(int(host.winId()))
    engine.open_media(str(FILM))

    def pump(seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.01)

    pump(2.0)
    result: dict[str, object] = {}
    for label in ("alone", "while_transcribing"):
        engine.seek(1000)
        pump(1.0)
        job = worker(media, "base", work) if label != "alone" else None
        pump(0.5)
        pos, dropped, started = (
            engine.get_playback_state().position_ms,
            engine.playback_stats().get("dropped", 0),
            time.perf_counter(),
        )
        pump(8.0)
        result[label] = {
            "advance_ratio": round(
                (engine.get_playback_state().position_ms - pos) / ((time.perf_counter() - started) * 1000), 3
            ),
            "dropped": engine.playback_stats().get("dropped", 0) - dropped,
        }
        if job is not None:
            job.wait(timeout=600)
        print(label, result[label])
    engine.close()
    host.close()
    return result


def main() -> int:
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "tools" / "engine-benchmark" / "results" / "ai_measure.json"
    )
    work = Path(tempfile.mkdtemp(prefix="babarify-m9-measure-"))
    wav, _ = make_speech(work)
    app = QApplication(sys.argv[:1])
    with __import__("wave").open(str(wav)) as w:
        audio_s = w.getnframes() / w.getframerate()
    rows = accuracy(wav, work)
    for row in rows:
        row["audio_s"] = round(audio_s, 1)
        row["speed_x"] = round(audio_s / float(row["wall_s"]), 1)  # type: ignore[arg-type]
    data = {"cpu": os.cpu_count(), "speech": rows, "playback": playback(app, wav, work)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
