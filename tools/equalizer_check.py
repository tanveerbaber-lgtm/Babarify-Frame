"""Check that libVLC's equalizer changes real audio output (M7), using the adapter's API calls.

Plays a generated 1 kHz tone (-12 dBFS) into memory through libVLC audio callbacks and reports
the RMS level with no equalizer, with the 1 kHz band cut, with the preamp lowered, and after
the equalizer is removed, all changed while playing. Requires ffmpeg (as make_media.py does).
The windowed RMS is buffered, so it shows direction and rough size, not exact dB.
Usage:  python tools/equalizer_check.py [out.json]
"""

from __future__ import annotations

import array
import ctypes
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from babarify_frame.playback.adapters.libvlc import _load_vlc

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "tools" / "engine-benchmark" / "results" / "equalizer_check.json"
    )
    vlc = _load_vlc()
    tone = Path(tempfile.mkdtemp(prefix="babarify-eq-")) / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=12",
         "-af", "volume=-12dB", "-ac", "2", str(tone)],
        check=True,
    )  # fmt: skip
    instance = vlc.Instance(["--no-video"])
    player = instance.media_player_new()
    samples = array.array("h")
    lock = threading.Lock()

    @vlc.CallbackDecorators.AudioPlayCb  # type: ignore[untyped-decorator]
    def play(_data: Any, buf: Any, count: int, _pts: Any) -> None:
        with lock:
            samples.frombytes(ctypes.string_at(buf, count * 4))

    player.audio_set_callbacks(play, None, None, None, None, None)
    player.audio_set_format("S16N", 48000, 2)
    player.set_media(instance.media_new_path(str(tone)))
    player.play()

    def rms(seconds: float = 1.0) -> int:
        with lock:
            start = len(samples)
        time.sleep(seconds)
        with lock:
            window = samples[start:]
        return round((sum(x * x for x in window) / max(1, len(window))) ** 0.5)

    def equalizer(band_db: float, preamp_db: float) -> Any:
        settings = vlc.AudioEqualizer()  # same calls as LibVlcEngine._apply_equalizer
        settings.set_preamp(preamp_db)
        for index in range(vlc.libvlc_audio_equalizer_get_band_count()):
            settings.set_amp_at_index(band_db if index == 5 else 0.0, index)  # band 5 = 1 kHz
        return settings

    time.sleep(0.8)
    rows = [{"case": "no equalizer", "rms": rms()}]
    for case, band, preamp in (("1 kHz band -20 dB", -20.0, 0.0), ("preamp -12 dB", 0.0, -12.0)):
        settings = equalizer(band, preamp)
        player.set_equalizer(settings)
        settings.release()
        time.sleep(0.5)
        rows.append({"case": case, "rms": rms()})
    player.set_equalizer(None)
    time.sleep(0.5)
    rows.append({"case": "equalizer removed", "rms": rms()})
    player.stop()
    for row in rows:
        print(f"{row['case']:20} rms {row['rms']}")
    reference = rows[0]["rms"]
    ok = rows[1]["rms"] < reference / 4 and rows[2]["rms"] < reference / 2 and rows[3]["rms"] > reference / 2
    print("equalizer changes output:", "yes" if ok else "NO")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows, "ok": ok}, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
