"""M14: play the test clips through both engines in the iOS Simulator and record results.

Runs on a Mac (GitHub's hosted runner). Writes results.json and screenshots/ into --output.
Simulator results say nothing about real iPhone decoders, battery or sound.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

BUNDLE_ID = "com.babarify.frame.BabarifyProbe"
ENGINES = ("avplayer", "vlckit")
VIDEO = [
    "h264_aac.mp4", "h264_aac.mkv", "h264_ac3.ts", "hevc8_aac.mp4", "hevc10_aac.mp4", "vp9_opus.webm",
    "vp8_vorbis.webm", "av1_opus.mkv", "mpeg2_mp2.mpg", "mpeg4_mp3.avi", "wmv2_wma.wmv",
    "theora_vorbis.ogv", "multitrack.mkv",
]  # fmt: skip
AUDIO = [
    "audio_aac.m4a", "audio_mp3.mp3", "audio_flac.flac", "audio_opus.opus", "audio_vorbis.ogg",
    "audio_ac3.ac3", "audio_pcm.wav",
]  # fmt: skip
DAMAGED = ["truncated.mp4", "not_media.mp4", "empty.mp4"]
PLAY_SECONDS = 7


def simctl(*arguments: str, check: bool = True) -> str:
    done = subprocess.run(["xcrun", "simctl", *arguments], capture_output=True, text=True, timeout=180)
    if check and done.returncode != 0:
        raise RuntimeError(f"simctl {arguments[0]}: {done.stderr.strip()}")
    return done.stdout


def launch(engine: str, media: str, **extra: str) -> None:
    arguments = ["launch", "--terminate-running-process", "booted", BUNDLE_ID]
    arguments += ["-engine", engine, "-media", media]
    for key, value in extra.items():
        arguments += [f"-{key}", value]
    simctl(*arguments)


def result_file() -> Path:
    return (
        Path(simctl("get_app_container", "booted", BUNDLE_ID, "data").strip()) / "Documents" / "result.json"
    )


def read_result() -> dict[str, object]:
    try:
        return json.loads(result_file().read_text("utf-8"))
    except (OSError, ValueError) as error:
        return {"error": f"no result: {error}", "positions_ms": [], "events": []}


def picture(path: Path) -> dict[str, int]:
    """Samples the middle of the screen, away from the status bar and home indicator."""
    simctl("io", "booted", "screenshot", str(path))
    image = Image.open(path).convert("L")
    width, height = image.size
    samples = [
        int(image.getpixel((width * x // 12, height * y // 12))) for x in range(1, 12) for y in range(3, 10)
    ]
    return {"max_lightness": max(samples), "distinct": len(set(samples))}


def verdict(run: dict[str, object], *, video: bool) -> str:
    positions = [int(value) for value in run.get("positions_ms", [])]  # type: ignore[attr-defined]
    advanced = positions[-1] - positions[0] if positions else 0
    if run.get("error"):
        return "error"
    if advanced < 2000:
        return "no progress"
    if video and int(run["picture"]["distinct"]) < 3:  # type: ignore[index]
        return "no picture"
    return "plays"


def play(
    engine: str, media: str, shots: Path, seconds: float = PLAY_SECONDS, **extra: str
) -> dict[str, object]:
    # Remove the last run's file so a failed launch cannot report old results.
    result_file().unlink(missing_ok=True)
    launch(engine, media, **extra)
    time.sleep(seconds)
    shot = shots / f"{engine}-{media}-{'-'.join(extra) or 'play'}.png"
    measured = picture(shot)
    run = read_result()
    run["picture"] = measured
    return run


def leave_and_return(engine: str, shots: Path) -> dict[str, object]:
    result_file().unlink(missing_ok=True)
    launch(engine, "long_60s.mp4")
    time.sleep(6)
    simctl("launch", "booted", "com.apple.Preferences")
    time.sleep(4)
    away = read_result()
    simctl("launch", "booted", BUNDLE_ID)
    time.sleep(5)
    run = read_result()
    run["picture"] = picture(shots / f"{engine}-return.png")
    run["position_while_away_ms"] = away.get("position_ms")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    shots = args.output / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {"runtime": simctl("list", "runtimes", "--json")}
    results["runtime"] = [
        runtime["name"]
        for runtime in json.loads(str(results["runtime"]))["runtimes"]
        if runtime["isAvailable"]
    ]

    def save() -> None:
        (args.output / "results.json").write_text(json.dumps(results, indent=1), "utf-8")

    for engine in ENGINES:
        files: dict[str, object] = {}
        results[engine] = {"files": files}
        for media, video in [(name, True) for name in VIDEO + DAMAGED] + [(name, False) for name in AUDIO]:
            run = play(engine, media, shots)
            run["verdict"] = verdict(run, video=video)
            files[media] = run
            print(engine, media, run["verdict"], run.get("error") or "", flush=True)
            save()
        run = play(engine, "h264_aac.mp4", shots, subtitle="subs.srt")
        run["verdict"] = verdict(run, video=True)
        files["h264_aac.mp4+subs.srt"] = run
        print(engine, "subtitle", run["verdict"], run.get("error") or "", flush=True)
        extra = results[engine]
        assert isinstance(extra, dict)
        extra["seek"] = play(engine, "long_60s.mp4", shots, seekAfterMs="3000", seekToMs="20000")
        extra["rotate"] = play(engine, "long_60s.mp4", shots, seconds=8, rotateAfterMs="3000")
        extra["leave_and_return"] = leave_and_return(engine, shots)
        print(engine, "lifecycle done", flush=True)
        save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
