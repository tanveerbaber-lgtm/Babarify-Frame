"""M12: play the test media through both Android prototypes on a real device and record results.

Installs the two prototype APKs, copies media into each app's private folder, plays each file and
reads the measurements the app logs. Results are written after every run, so a lost USB connection
keeps what was measured. `--cleanup` uninstalls both apps, which also removes the copied media.

Nothing outside the two prototype packages is installed, changed or removed on the device.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated"
APKS = ROOT / "android" / "prototype" / "app" / "build" / "outputs" / "apk"
ADB = Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
BASE_PACKAGE = "com.babarify.frame.prototype"
ENGINES = ("media3", "vlc")
TAG = "BabarifyProbe"
MIN_BATTERY = 8
PLAY_SECONDS = 9
MAX_ATTEMPTS = 3

VIDEO = [
    "h264_1080p30_aac.mp4",
    "c_h264_aac_1080p60.mp4",
    "e_h264_720p120.mp4",
    "c_h264_aac_720p.mkv",
    "c_h264_aac_portrait_1080x1920.mp4",
    "e_rotated_90_h264.mp4",
    "c_h264_ac3_720p.ts",
    "c_hevc10_aac_1080p.mp4",
    "hevc_2160p30_aac.mkv",
    "vp9_1080p30_opus.webm",
    "av1_1080p30_opus.mkv",
    "c_vp8_vorbis_720p.webm",
    "c_mpeg2_mp2_576p.mpg",
    "e_interlaced_mpeg2_1080i.ts",
    "c_mpeg4_mp3_480p.avi",
    "c_wmv2_wmav2_480p.wmv",
    "c_theora_vorbis_480p.ogv",
    "multitrack_720p.mkv",
    "e_mkv_no_cues.mkv",
]
AUDIO = [
    "c_audio_aac.m4a",
    "c_audio_mp3.mp3",
    "c_audio_flac.flac",
    "c_audio_opus.opus",
    "c_audio_vorbis.ogg",
    "c_audio_ac3_51.ac3",
    "c_audio_pcm.wav",
]
DAMAGED = ["e_corrupt_midstream.ts", "truncated.mp4", "not_media.mp4", "e_empty.mp4"]
SUBTITLES = [("s_sidecar_720p.mp4", "s_ext.srt"), ("s_sidecar_720p.mp4", "s_ext.ass")]


class PhoneLocked(RuntimeError):
    pass


def adb(*args: str, timeout: float = 120, check: bool = True) -> str:
    done = subprocess.run(
        [str(ADB), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )
    if check and done.returncode != 0:
        raise RuntimeError(f"adb {args[0]} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout


def wait_for_device() -> None:
    adb("wait-for-device", timeout=600)


def battery_level() -> int:
    for line in adb("shell", "dumpsys battery").splitlines():
        if line.strip().startswith("level:"):
            return int(line.split(":")[1])
    raise RuntimeError("battery level not reported")


def package(engine: str) -> str:
    return f"{BASE_PACKAGE}.{engine}"


def device_dir(engine: str) -> str:
    return f"/storage/emulated/0/Android/data/{package(engine)}/files"


def install(engine: str) -> None:
    adb("install", "-r", str(APKS / engine / "release" / f"app-{engine}-arm64-v8a-release.apk"), timeout=300)
    # The app must create its own folder: one made by adb belongs to the shell and the app cannot read it.
    adb("shell", f"am start -S -W -n {package(engine)}/{BASE_PACKAGE}.MainActivity")


def push(engine: str, names: list[str]) -> None:
    for name in names:
        for attempt in range(MAX_ATTEMPTS):
            try:
                adb("push", str(MEDIA / name), f"{device_dir(engine)}/{name}", timeout=300)
                break
            except RuntimeError:
                # This phone's USB link has dropped mid-copy; wait for it instead of losing the run.
                if attempt == MAX_ATTEMPTS - 1:
                    raise
                print(f"copy of {name} interrupted, waiting for the phone", flush=True)
                adb("wait-for-device", timeout=600)
    # Copying happens with the app on screen, whose keep-screen-on flag stops the phone locking.
    adb("shell", f"am force-stop {package(engine)}")


def play(
    engine: str,
    media: str,
    *,
    subtitle: str | None = None,
    seconds: float = PLAY_SECONDS,
    extras: tuple[str, ...] = (),
) -> dict[str, object]:
    """Starts one file from a stopped app and returns what the app logged, plus a screenshot check."""
    base = f"file://{device_dir(engine)}"
    command = ["am", "start", "-S", "-W", "-n", f"{package(engine)}/{BASE_PACKAGE}.MainActivity"]
    command += ["--es", "media", f"{base}/{media}"]
    if subtitle:
        command += ["--es", "subtitle", f"{base}/{subtitle}"]
    command += extras
    adb("logcat", "-c", check=False)
    adb("shell", shlex.join(command))
    time.sleep(seconds)
    require_unlocked()
    app_pid = adb("shell", f"pidof {package(engine)}", check=False).strip()
    picture = screenshot()
    # Going to the home screen stops the activity, which releases the engine and logs final stats.
    adb("shell", "input keyevent KEYCODE_HOME")
    time.sleep(1)
    events, codecs = read_log(app_pid)
    adb("shell", f"am force-stop {package(engine)}")
    return {**summarise(events), "codecs": codecs, "picture": picture}


def read_log(app_pid: str) -> tuple[list[dict[str, object]], list[str]]:
    events: list[dict[str, object]] = []
    codecs: set[str] = set()
    # Only this app's probe and codec lines are kept; other apps' log lines are never stored.
    for line in adb("logcat", "-d", "-v", "brief").splitlines():
        if f"{TAG}" in line and "{" in line:
            try:
                events.append(json.loads(line[line.index("{") :]))
            except json.JSONDecodeError:
                continue
        elif "Created component [" in line and f"({app_pid.rjust(5)})" in line:
            codecs.add(line.split("Created component [")[1].split("]")[0])
    return events, sorted(codecs)


def summarise(events: list[dict[str, object]]) -> dict[str, object]:
    def named(name: str) -> list[dict[str, object]]:
        return [event for event in events if event["event"] == name]

    ticks = named("tick")
    positions = [int(str(event["position_ms"])) for event in ticks]
    first = named("first_frame")
    tracks = named("tracks")
    stats = named("stats")
    return {
        "first_frame_ms": first[0]["after_ms"] if first else None,
        "video_decoder": [event["name"] for event in named("video_decoder")],
        "audio_decoder": [event["name"] for event in named("audio_decoder")],
        "errors": [event.get("code") or event.get("message") for event in named("error")],
        "tracks": tracks[-1]["tracks"] if tracks else [],
        "stats": stats[-1] if stats else None,
        "duration_ms": ticks[-1]["duration_ms"] if ticks else None,
        "positions_ms": positions,
        "advanced_ms": positions[-1] - positions[0] if positions else 0,
        "events": [
            event for event in events if event["event"] in ("seek", "rotate", "stopped", "open", "ended")
        ],
    }


def screenshot() -> dict[str, object] | None:
    """Reports whether the middle of the screen shows a picture; the image itself is not kept."""
    done = subprocess.run([str(ADB), "exec-out", "screencap", "-p"], capture_output=True, timeout=60)
    image = QImage.fromData(done.stdout)
    if image.isNull():
        return None
    samples = [
        image.pixelColor(image.width() * x // 12, image.height() * y // 12).lightness()
        for x in range(3, 10)
        for y in range(3, 10)
    ]
    return {"max_lightness": max(samples), "distinct": len(set(samples))}


def verdict(run: dict[str, object], *, video: bool) -> str:
    if run["errors"]:
        return "error"
    if int(str(run["advanced_ms"])) < 2000:
        return "no progress"
    if not video:
        return "plays"
    picture = run["picture"]
    if not isinstance(picture, dict) or int(picture["max_lightness"]) < 20:
        return "no picture"
    return "plays"


def plays_audio(engine: str) -> bool:
    """True when the system lists a started audio player belonging to this app."""
    listing = adb("shell", f"pm list packages -U {package(engine)}", check=False)
    if " uid:" not in listing:
        raise RuntimeError(f"no uid for {package(engine)}")
    uid = listing.split(" uid:")[1].split()[0]
    return any(
        "state:started" in line and f"u/pid:{uid}/" in line
        for line in adb("shell", "dumpsys audio").splitlines()
    )


def wait_until_unlocked() -> None:
    """Only waits: the phone stays the owner's to unlock, and a locked screen is not a playback failure."""
    announced = False
    while not is_unlocked():
        if not announced:
            print("waiting: unlock the phone", flush=True)
            announced = True
        time.sleep(5)


def is_unlocked() -> bool:
    return "mDreamingLockscreen=false" in adb("shell", "dumpsys window", timeout=60)


def require_unlocked() -> None:
    """A phone that locked during a run says nothing about the engine, so the run does not count."""
    if not is_unlocked():
        raise PhoneLocked("the phone locked during this run")


def lifecycle(engine: str, out: dict[str, object], save: Callable[[], None]) -> None:
    media = "h264_1080p30_aac.mp4"
    seek = ("--el", "seek_after_ms", "4000", "--el", "seek_to_ms", "20000")
    out["seek"] = play(engine, media, extras=seek)
    save()
    rotate = ("--el", "rotate_after_ms", "5000")
    out["rotate"] = play(engine, media, extras=rotate, seconds=11)
    save()

    # Leave and come back without restarting the app: position must survive, nothing plays behind.
    adb("logcat", "-c", check=False)
    start = ["am", "start", "-S", "-W", "-n", f"{package(engine)}/{BASE_PACKAGE}.MainActivity"]
    adb("shell", shlex.join([*start, "--es", "media", f"file://{device_dir(engine)}/{media}"]))
    time.sleep(6)
    adb("shell", "input keyevent KEYCODE_HOME")
    time.sleep(5)
    audio_while_away = plays_audio(engine)
    adb("shell", f"am start -W -n {package(engine)}/{BASE_PACKAGE}.MainActivity")
    time.sleep(5)
    require_unlocked()
    app_pid = adb("shell", f"pidof {package(engine)}", check=False).strip()
    picture = screenshot()
    adb("shell", "input keyevent KEYCODE_HOME")
    time.sleep(1)
    events, codecs = read_log(app_pid)
    adb("shell", f"am force-stop {package(engine)}")
    out["background_resume"] = {
        **summarise(events),
        "codecs": codecs,
        "picture": picture,
        "audio_while_away": audio_while_away,
    }
    save()


def run(output: Path, engines: tuple[str, ...]) -> int:
    wait_for_device()
    results: dict[str, object] = json.loads(output.read_text("utf-8")) if output.exists() else {}
    results["device"] = {
        prop: adb("shell", "getprop", prop).strip()
        for prop in ("ro.product.model", "ro.build.version.release", "ro.build.version.sdk", "ro.soc.model")
    }

    def save() -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=1, ensure_ascii=False), "utf-8")

    cases: list[tuple[str, str | None, bool]] = [(name, None, True) for name in VIDEO + DAMAGED]
    cases += [(name, None, False) for name in AUDIO]
    cases += [(name, sub, True) for name, sub in SUBTITLES]
    names = sorted({name for name, _, _ in cases} | {sub for _, sub, _ in cases if sub})

    for engine in engines:
        install(engine)
        push(engine, names)
        engine_results = results.setdefault(engine, {})
        assert isinstance(engine_results, dict)
        files = engine_results.setdefault("files", {})
        for name, subtitle, video in cases:
            key = f"{name}+{subtitle}" if subtitle else name
            if key in files and files[key]["verdict"] != "not measured":
                continue
            level = battery_level()
            if level < MIN_BATTERY:
                print(f"stopping: battery at {level}%")
                return 2
            outcome: dict[str, object] = {"verdict": "not measured"}
            for _ in range(MAX_ATTEMPTS):
                try:
                    wait_until_unlocked()
                    outcome = play(engine, name, subtitle=subtitle, seconds=PLAY_SECONDS)
                    outcome["verdict"] = verdict(outcome, video=video)
                    break
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    wait_for_device()
                    outcome = {"verdict": "not measured", "problem": str(error)}
            files[key] = outcome
            print(engine, key, outcome["verdict"], outcome.get("first_frame_ms"), flush=True)
            save()
        for _ in range(MAX_ATTEMPTS):
            try:
                wait_until_unlocked()
                lifecycle(engine, engine_results.setdefault("lifecycle", {}), save)
                break
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                print(engine, "lifecycle retry:", error, flush=True)
                wait_for_device()
        print(engine, "lifecycle done", flush=True)
    return 0


def cleanup() -> int:
    for engine in ENGINES:
        print(package(engine), adb("uninstall", package(engine), check=False).strip())
    remaining = adb("shell", f"pm list packages {BASE_PACKAGE}", check=False).strip()
    print("prototype packages left:", remaining or "none")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/milestones/M12/evidence/android_probe.json"
    )
    parser.add_argument("--engine", choices=ENGINES, action="append")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="one file per engine, to check the setup")
    args = parser.parse_args()
    if args.cleanup:
        return cleanup()
    if args.smoke:
        VIDEO[:] = VIDEO[:1]
        AUDIO.clear()
        DAMAGED.clear()
        SUBTITLES.clear()
    return run(args.output, tuple(args.engine or ENGINES))


if __name__ == "__main__":
    sys.exit(main())
