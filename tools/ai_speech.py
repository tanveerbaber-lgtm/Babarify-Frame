"""Local test speech for M9 tools: Windows speech synthesis, no download.

``make_speech(folder)`` writes ``speech.wav`` (3 s of silence, then TEXT) and, when ffmpeg is
available, ``speech.mp4`` (the speech under a 1280x720 test picture).
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

TEXT = (
    "The harbour lights came on one by one as the fishing boats returned. "
    "Maria counted seven boats, then eight, and waited for her brother. "
    "The wind had turned cold, and the market stalls were closing early. "
    "An old man sold roasted chestnuts from a cart near the lighthouse. "
    "When the last boat finally appeared, the whole village walked down to the water. "
    "Nobody spoke until the ropes were tied and the engine was quiet. "
    "Then everyone laughed at once, and somebody started to sing."
)
LEAD_IN_S = 3.0


def make_speech(folder: Path) -> tuple[Path, Path | None]:
    folder.mkdir(parents=True, exist_ok=True)
    raw, wav, mp4 = folder / "raw.wav", folder / "speech.wav", folder / "speech.mp4"
    script = (
        "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{raw}'); $s.Speak('{TEXT}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True)
    with wave.open(str(raw)) as src, wave.open(str(wav), "wb") as dst:
        dst.setparams(src.getparams())
        silence = b"\x00" * int(LEAD_IN_S * src.getframerate()) * src.getsampwidth() * src.getnchannels()
        dst.writeframes(silence + src.readframes(src.getnframes()))
    if shutil.which("ffmpeg") is None:
        return wav, None
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=75",
         "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
         "-c:a", "aac", "-shortest", str(mp4)],
        check=True,
    )  # fmt: skip
    return wav, mp4
