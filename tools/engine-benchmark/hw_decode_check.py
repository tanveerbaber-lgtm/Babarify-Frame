"""Hardware-decoding truthfulness and CPU check (M4).

For each engine x hardware setting (Automatic / Off) x media, plays the file in a FRESH
process for a fixed window and records what the app reports as the decoder, the process
CPU (% of one core) and dropped frames. Expected, if reporting is honest:
  * Off  -> always "software"
  * Automatic + a codec the GPU cannot decode (e.g. AV1, VP8 on Intel UHD 620) -> "software"
  * Automatic + a supported codec -> "hardware (...)" and clearly lower CPU than Off

Usage:
    python tools/engine-benchmark/hw_decode_check.py [--engines libvlc mpv] [--seconds 5]
Writes results/hw_decode_check.json (committed as evidence).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MEDIA_DIR = HERE.parents[1] / "tests" / "fixtures" / "media" / "generated"
MEDIA = [
    "h264_1080p30_aac.mp4",
    "hevc_2160p30_aac.mkv",
    "e_hevc10_2160p.mkv",
    "vp9_1080p30_opus.webm",
    "c_mpeg2_mp2_576p.mpg",
    "av1_1080p30_opus.mkv",
    "c_vp8_vorbis_720p.webm",
    "c_audio_flac.flac",
]


def one_run(engine: str, hardware: bool, media: str, seconds: float) -> dict[str, Any]:
    """Runs inside a child process."""
    import psutil
    from PySide6.QtWidgets import QApplication, QWidget

    from babarify_frame.core.models import EngineOptions
    from babarify_frame.core.models import PlaybackState as S
    from babarify_frame.playback.factory import default_factory

    app = QApplication(sys.argv[:1])
    window = QWidget()
    window.resize(1280, 720)
    window.show()
    app.processEvents()
    eng = default_factory().create(engine, EngineOptions(hardware_decoding=hardware))
    out: dict[str, Any] = {
        "engine": engine,
        "hardware_setting": "auto" if hardware else "off",
        "media": media,
    }
    try:
        eng.set_video_output(int(window.winId()))
        eng.open_media(str(MEDIA_DIR / media))
        end = time.perf_counter() + 15
        while eng.get_playback_state().state is not S.PLAYING and time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.01)

        def pump(s: float) -> None:
            stop = time.perf_counter() + s
            while time.perf_counter() < stop:
                app.processEvents()
                time.sleep(0.01)

        pump(1.5)
        proc = psutil.Process()
        before_stats = dict(eng.playback_stats())
        t0, c0 = time.perf_counter(), sum(proc.cpu_times()[:2])
        pump(seconds)
        t1, c1 = time.perf_counter(), sum(proc.cpu_times()[:2])
        after_stats = dict(eng.playback_stats())
        diag = eng.diagnostics()
        out.update(
            state=eng.get_playback_state().state.value,
            decoder=diag.get("decoder"),
            raw_hwdec=diag.get("hwdec"),
            cpu_pct_one_core=round(100 * (c1 - c0) / (t1 - t0), 1),
            dropped=after_stats.get("dropped", 0) - before_stats.get("dropped", 0),
        )
    finally:
        eng.close()
        window.close()
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--engines", nargs="+", default=["libvlc", "mpv"])
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--child", nargs=3, metavar=("ENGINE", "HW", "MEDIA"))
    a = p.parse_args()
    if a.child:
        engine, hw, media = a.child
        print("RESULT " + json.dumps(one_run(engine, hw == "auto", media, a.seconds)), flush=True)
        return 0

    rows = []
    for engine in a.engines:
        for media in MEDIA:
            for hw in ("auto", "off"):
                cmd = [sys.executable, __file__, "--child", engine, hw, media, "--seconds", str(a.seconds)]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")), None)
                row = (
                    json.loads(line[7:])
                    if line
                    else {
                        "engine": engine,
                        "hardware_setting": hw,
                        "media": media,
                        "failure": f"exit {proc.returncode}",
                    }
                )
                row["exit_code"] = proc.returncode
                rows.append(row)
                print(
                    f"{engine:6} {hw:4} {media:24} decoder={row.get('decoder')!s:28} "
                    f"cpu={row.get('cpu_pct_one_core')!s:>5}% dropped={row.get('dropped')} "
                    f"exit={proc.returncode}",
                    flush=True,
                )
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "hw_decode_check.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    off_rows = [r for r in rows if r["hardware_setting"] == "off" and "decoder" in r]
    honest_off = all(r["decoder"] in ("software", "no video") for r in off_rows)
    print(f"Off always reported as software: {honest_off}")
    return 0 if honest_off else 1


if __name__ == "__main__":
    sys.exit(main())
