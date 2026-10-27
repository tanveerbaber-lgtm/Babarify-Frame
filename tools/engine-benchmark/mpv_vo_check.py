"""Follow-up check: where do mpv's dropped frames on 4K HEVC come from, and does the renderer matter?

Plays the 4K HEVC clip for 8 s in a 1280x720 Qt window with each video output and
prints decoder vs. video-output drop counts. Usage:
    python tools/engine-benchmark/mpv_vo_check.py [runs]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mpv import MpvEngine

MEDIA = Path(__file__).resolve().parents[2] / "tests/fixtures/media/generated/hevc_2160p30_aac.mkv"


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.005)


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    app = QApplication(sys.argv[:1])
    window = QWidget()
    window.resize(1280, 720)
    window.show()
    for vo in ("gpu-next", "gpu"):
        for run in range(runs):
            engine = MpvEngine({"vo": vo})
            engine.initialize()
            engine.set_video_output(int(window.winId()))
            engine.open_media(str(MEDIA))
            deadline = time.perf_counter() + 15
            while engine.state is not S.PLAYING and time.perf_counter() < deadline:
                pump(app, 0.05)
            pump(app, 1.0)
            before = engine.playback_stats()
            pump(app, 8.0)
            after = engine.playback_stats()
            diag = engine.diagnostics()
            print(
                f"vo={vo:8} run={run + 1} vo_drops={after['dropped_vo'] - before['dropped_vo']:4} "
                f"decoder_drops={after['dropped_decoder'] - before['dropped_decoder']:4} "
                f"hwdec={diag['hwdec']} current_vo={diag['video_output']}",
                flush=True,
            )
            engine.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
