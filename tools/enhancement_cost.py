"""Measure the cost of M7 picture/sound controls on libVLC: CPU (% of one core) and dropped frames.

Each row: fresh engine, 1280x720 window, 1.5 s settle, 6 s measurement, Babarify process CPU.
Usage:  python tools/enhancement_cost.py [out.json]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import psutil
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from babarify_frame.core.enhancements import EqualizerSettings, PictureSettings, VideoTransform
from babarify_frame.core.models import EngineOptions
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.factory import default_factory

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated"
FILES = ("h264_1080p30_aac.mp4", "hevc_2160p30_aac.mkv")
SETTLE_S, MEASURE_S = 1.5, 6.0
ADJUST = PictureSettings(brightness=1.2, contrast=1.1, saturation=1.3, hue=10.0)
EQ = EqualizerSettings(True, "", -3.0, (6.0, 4.0, 2.0, 0.0, -2.0, -2.0, 0.0, 2.0, 4.0, 6.0))

CASES: dict[str, dict[str, Any]] = {
    "baseline": {},
    "picture adjust": {"picture": ADJUST},
    "equalizer": {"equalizer": EQ},
    "aspect 4:3 + zoom fit": {"geometry": ("4:3", "", 0.0)},
    "rotate 90": {"transform": VideoTransform.ROTATE_90},
}


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def run_case(
    app: QApplication, host: QWidget, file: str, hardware: bool, case: dict[str, Any]
) -> dict[str, Any]:
    transform = case.get("transform", VideoTransform.NONE)
    engine = default_factory().create(
        "libvlc", EngineOptions(hardware_decoding=hardware, video_transform=transform)
    )
    engine.set_video_output(int(host.winId()))
    if "picture" in case:
        engine.set_picture(case["picture"])
    if "equalizer" in case:
        engine.set_equalizer(case["equalizer"])
    engine.open_media(str(MEDIA / file))
    deadline = time.perf_counter() + 15
    while engine.get_playback_state().state is not S.PLAYING and time.perf_counter() < deadline:
        pump(app, 0.05)
    if "geometry" in case:
        engine.set_video_geometry(*case["geometry"])
    pump(app, SETTLE_S)
    process = psutil.Process()
    stats_before = engine.playback_stats() if hasattr(engine, "playback_stats") else {}
    process.cpu_percent(None)
    pump(app, MEASURE_S)
    cpu = process.cpu_percent(None)
    stats_after = engine.playback_stats() if hasattr(engine, "playback_stats") else {}
    decoder = engine.diagnostics().get("decoder", "")
    state = engine.get_playback_state().state.value
    engine.close()
    dropped = stats_after.get("dropped", 0) - stats_before.get("dropped", 0)
    return {"cpu_pct": round(cpu, 1), "dropped": dropped, "decoder": decoder, "state": state}


def main() -> int:
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "tools" / "engine-benchmark" / "results" / "enhancement_cost.json"
    )
    app = QApplication(sys.argv[:1])
    host = QWidget()
    host.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    host.resize(1280, 720)
    host.show()
    results = []
    for file in FILES:
        for hardware in (True, False):
            for name, case in CASES.items():
                row = {"file": file, "decoding": "hardware" if hardware else "software", "case": name}
                row.update(run_case(app, host, file, hardware, case))
                results.append(row)
                print(
                    f"{file:24} {row['decoding']:8} {name:22} cpu {row['cpu_pct']:6.1f} %  dropped "
                    f"{row['dropped']:4}  {row['decoder']}  {row['state']}",
                    flush=True,
                )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"measure_s": MEASURE_S, "results": results}, indent=2), encoding="utf-8")
    host.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
