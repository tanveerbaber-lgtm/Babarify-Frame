"""Benchmark orchestrator: repeated trials of libVLC vs mpv, each in a fresh process.

Usage:
    python tools/engine-benchmark/bench.py --trials 5

Writes:
    results/raw/run-<timestamp>.json   every trial result (git-ignored)
    results/summary.json, summary.md   medians and ranges (committed as evidence)

Engine order alternates between trials to avoid systematic ordering bias.
Each trial is a new Python process, so every trial includes DLL loading and
engine start-up. Trial 1 follows media generation, so the OS file cache is
warm for all trials; true cold starts (after reboot) are not measured.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import psutil

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
ENGINES = ["libvlc", "mpv"]
PERF_MEDIA = ["h264_1080p30_aac.mp4", "hevc_2160p30_aac.mkv", "vp9_1080p30_opus.webm", "av1_1080p30_opus.mkv"]
TRIAL_TIMEOUT = 180


def machine_info() -> dict[str, Any]:
    def ps(cmd: str) -> Any:
        try:
            raw = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd + " | ConvertTo-Json -Compress"],
                capture_output=True,
                text=True,
                timeout=60,
            ).stdout
            return json.loads(raw) if raw.strip() else None
        except (subprocess.SubprocessError, json.JSONDecodeError):
            return None

    battery = psutil.sensors_battery()
    from babarify_frame.playback.factory import default_factory

    factory = default_factory()
    engines = {n: factory.probe(n).version for n in ENGINES}
    manifest = json.loads((HERE / "media-manifest.json").read_text(encoding="utf-8"))
    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "os": ps("Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture"),
        "cpu": ps(
            "Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors"
        ),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "gpus": ps(
            "Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, "
            "CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate"
        ),
        "power": {
            "on_ac": battery.power_plugged if battery else None,
            "battery_pct": battery.percent if battery else None,
        },
        "power_plan": subprocess.run(
            ["powercfg", "/getactivescheme"], capture_output=True, text=True
        ).stdout.strip(),
        "python": platform.python_version(),
        "packages": {p: version(p) for p in ("PySide6", "python-vlc", "mpv", "psutil")},
        "engines": engines,
        "media_ffmpeg": manifest["ffmpeg_version"],
    }


def run_trial(args: list[str]) -> dict[str, Any]:
    cmd = [sys.executable, str(HERE / "trial.py"), *args]
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TRIAL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "failure": f"timeout after {TRIAL_TIMEOUT}s", "args": args}
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("RESULT ")), None)
    if line is None:
        return {
            "ok": False,
            "failure": f"process exited {proc.returncode} without a result (crash?)",
            "stderr_tail": proc.stderr[-2000:],
            "args": args,
            "wall_s": time.perf_counter() - started,
        }
    result: dict[str, Any] = json.loads(line[len("RESULT ") :])
    result["exit_code"] = proc.returncode
    if proc.returncode != 0:
        result["ok"] = False
        result["stderr_tail"] = proc.stderr[-2000:]
    return result


def summarize(values: list[float]) -> dict[str, float] | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"median": statistics.median(values), "min": min(values), "max": max(values), "n": len(values)}


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"perf": {}, "tracks": {}, "errors": {}, "cycles": {}}
    for engine in ENGINES:
        for media in PERF_MEDIA:
            rs = [
                r
                for r in results
                if r.get("engine") == engine and r.get("scenario") == "perf" and r.get("media") == media
            ]
            ok = [r for r in rs if r.get("ok")]
            entry = {
                "trials": len(rs),
                "failures": [r.get("failure") or "seek timeout" for r in rs if not r.get("ok")],
                "init_ms": summarize([r.get("init_ms") for r in ok]),
                "open_to_playing_ms": summarize([r.get("open_to_playing_ms") for r in ok]),
                "open_to_first_position_ms": summarize([r.get("open_to_first_position_ms") for r in ok]),
                "open_to_progress_ms": summarize([r.get("open_to_progress_ms") for r in ok]),
                "seek_reported_ms": summarize([s for r in rs for s in (r.get("seek_reported_ms") or [])]),
                "displayed_frames": summarize([r.get("steady_displayed_frames") for r in ok]),
                "seek_ms": summarize([s for r in rs for s in (r.get("seek_ms") or [])]),
                "seek_timeouts": sum(1 for r in rs for s in (r.get("seek_ms") or []) if s is None),
                "cpu_pct_one_core": summarize([r.get("steady_cpu_pct_one_core") for r in ok]),
                "rss_mb_max": summarize([r.get("steady_rss_mb_max") for r in ok]),
                "dropped_frames": summarize([r.get("steady_dropped_frames") for r in ok]),
                "close_ms": summarize([r.get("close_ms") for r in ok]),
                "hwdec": sorted(
                    {(r.get("diagnostics") or {}).get("hwdec", "?") for r in rs if r.get("diagnostics")}
                ),
                "video_output": sorted(
                    {
                        (r.get("diagnostics") or {}).get("video_output", "?")
                        for r in rs
                        if r.get("diagnostics")
                    }
                ),
                "media_info": next((r.get("media_info") for r in ok if r.get("media_info")), None),
                "rejected_transitions": sorted({t for r in rs for t in r.get("rejected_transitions", [])}),
            }
            summary["perf"].setdefault(engine, {})[media] = entry
        for kind in ("tracks", "errors", "cycles"):
            summary[kind][engine] = [
                r for r in results if r.get("engine") == engine and r.get("scenario") == kind
            ]
    return summary


def fmt(stat: dict[str, float] | None, digits: int = 0) -> str:
    if not stat:
        return "n/a"
    f = f"{{:.{digits}f}}"
    return f"{f.format(stat['median'])} ({f.format(stat['min'])}–{f.format(stat['max'])})"


def write_markdown(info: dict[str, Any], summary: dict[str, Any], trials: int) -> str:
    lines = [
        f"# Engine benchmark summary — {info['date']}",
        "",
        f"Trials per engine × media: {trials}. Values: median (min–max). Generated by bench.py.",
        "",
        "Open→progress and Seek→resume are the comparable metrics (see trial.py); the engine-reported",
        "values (PLAYING event, position report after seek) are shown for reference only.",
        "",
        "| Engine | Media | Open→progress ms | Seek→resume ms | CPU % (1 core) | RSS MB | Dropped / 8 s "
        "| HW decoder | Failures | PLAYING event ms | Seek reported ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for engine, per_media in summary["perf"].items():
        for media, e in per_media.items():
            hw = "; ".join(h.split(" (")[0] for h in e["hwdec"])
            fails = len(e["failures"]) + e["seek_timeouts"]
            lines.append(
                f"| {engine} | {media} | {fmt(e['open_to_progress_ms'])} | {fmt(e['seek_ms'])} | "
                f"{fmt(e['cpu_pct_one_core'])} | {fmt(e['rss_mb_max'])} | {fmt(e['dropped_frames'])} | "
                f"{hw} | {fails} | {fmt(e['open_to_playing_ms'])} | {fmt(e['seek_reported_ms'])} |"
            )
    lines += ["", "| Engine | Init ms (DLL load + start) | Close ms |", "|---|---|---|"]
    for engine, per_media in summary["perf"].items():
        inits = [v for e in per_media.values() if e["init_ms"] for v in [e["init_ms"]["median"]]]
        closes = [v for e in per_media.values() if e["close_ms"] for v in [e["close_ms"]["median"]]]
        lines.append(
            f"| {engine} | median of medians {statistics.median(inits):.0f} | "
            f"median of medians {statistics.median(closes):.0f} |"
            if inits and closes
            else f"| {engine} | n/a | n/a |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=5)
    p.add_argument("--error-trials", type=int, default=3)
    p.add_argument("--steady", type=float, default=8.0)
    p.add_argument("--engines", nargs="+", default=ENGINES)
    a = p.parse_args()

    info = machine_info()
    print(json.dumps(info, indent=2), flush=True)
    results: list[dict[str, Any]] = []

    def record(r: dict[str, Any]) -> None:
        results.append(r)
        status = "ok" if r.get("ok") else f"FAIL {r.get('failure', '')}"
        print(
            f"  {r.get('engine', '?'):6} {r.get('scenario', '?'):6} {r.get('media') or '':24} {status}",
            flush=True,
        )

    for trial in range(a.trials):
        order = a.engines if trial % 2 == 0 else list(reversed(a.engines))
        print(f"perf trial {trial + 1}/{a.trials} order={order}", flush=True)
        for media in PERF_MEDIA:
            for engine in order:
                record(
                    run_trial(
                        [
                            "--engine",
                            engine,
                            "--scenario",
                            "perf",
                            "--media",
                            media,
                            "--steady",
                            str(a.steady),
                        ]
                    )
                    | {"trial": trial + 1}
                )
    for engine in a.engines:
        record(run_trial(["--engine", engine, "--scenario", "tracks"]))
        for _ in range(a.error_trials):
            record(run_trial(["--engine", engine, "--scenario", "errors"]))
        record(run_trial(["--engine", engine, "--scenario", "cycles"]))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RESULTS / "raw").mkdir(parents=True, exist_ok=True)
    (RESULTS / "raw" / f"run-{stamp}.json").write_text(
        json.dumps({"machine": info, "results": results}, indent=2, default=str), encoding="utf-8"
    )
    summary = build_summary(results)
    (RESULTS / "summary.json").write_text(
        json.dumps({"machine": info, "trials": a.trials, "summary": summary}, indent=2, default=str),
        encoding="utf-8",
    )
    (RESULTS / "summary.md").write_text(write_markdown(info, summary, a.trials), encoding="utf-8")
    print(f"wrote results/raw/run-{stamp}.json, results/summary.json, results/summary.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
