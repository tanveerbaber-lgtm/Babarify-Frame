"""Release check (M10): install, clean-environment run, AI worker, upgrade, rollback, uninstall.

Uses the installers in release/<version>/ (and a second, newer test build for the upgrade). It
installs into a throw-away folder for the current user, runs the installed program with a
stripped environment (Windows-only PATH, no Python/Babarify variables, empty profile folders),
and checks every module the running program has loaded comes from the install folder or Windows.
Usage:  python tools/release_check.py <old-setup.exe> <new-setup.exe> [out.json]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_speech import make_speech

ROOT = Path(__file__).resolve().parents[1]

MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated" / "h264_1080p30_aac.mp4"
APP_ID = "{6C6E6628-FE5B-4E93-ADA0-C13ADF7F99A2}_is1"
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
WINDOWS = os.environ.get("SYSTEMROOT", r"C:\Windows")


def clean_env(profile: Path) -> dict[str, str]:
    """What a fresh user account would have: Windows paths only, empty app-data folders."""
    # Python keeps Windows variable names in upper case.
    keep = {
        "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "NUMBER_OF_PROCESSORS", "OS",
        "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "USERNAME", "USERDOMAIN", "TEMP", "TMP",
    }  # fmt: skip
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["PATH"] = f"{WINDOWS}\\system32;{WINDOWS};{WINDOWS}\\System32\\Wbem"
    for name in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        folder = profile / name
        folder.mkdir(parents=True, exist_ok=True)
        env[name] = str(folder)
    return env


def install(setup: Path, target: Path, log: Path, tasks: str = "") -> int:
    args = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
            f"/DIR={target}", f"/LOG={log}"]  # fmt: skip
    if tasks:
        args.append(f"/TASKS={tasks}")
    return subprocess.run(args, timeout=600).returncode


def file_version(exe: Path) -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"(Get-Item '{exe}').VersionInfo.ProductVersion"],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    return out.stdout.strip()


def reg_value(path: str, name: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


def run_app(app: Path, env: dict[str, str], media: Path, seconds: int = 20) -> dict[str, object]:
    process = psutil.Popen([str(app), str(media), "--smoke-test", str(seconds * 1000)], env=env)
    foreign: set[str] = set()
    loaded = 0
    started = time.time()
    while process.poll() is None and time.time() - started < seconds + 30:
        try:
            for item in process.memory_maps():
                path = item.path
                loaded += 1
                inside = path.lower().startswith(str(app.parent).lower())
                if not inside and not path.lower().startswith(WINDOWS.lower()):
                    foreign.add(path)
        except psutil.Error:
            pass
        time.sleep(1.0)
    code = process.wait(timeout=60)
    log = Path(env["LOCALAPPDATA"]) / "Babarify" / "Frame" / "logs" / "app.log"
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    return {
        "exit": code,
        "foreign_modules": sorted(foreign),
        "dev_paths_loaded": sorted(
            p for p in foreign if "babarify vision" in p.lower() or ".venv" in p.lower()
        ),
        "log_started": "started" in text,
        "log_played": "smoke test: state=playing" in text or "smoke test: state=paused" in text,
        "engine_ready": [line.split("INFO ")[-1] for line in text.splitlines() if "engine ready in" in line],
        "log_tail": text.strip().splitlines()[-4:],
        "crash_log": (log.parent / "crash.log").read_text(encoding="utf-8")[-400:]
        if (log.parent / "crash.log").is_file()
        else "",
    }


def main() -> int:
    old_setup, new_setup = Path(sys.argv[1]), Path(sys.argv[2])
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "release" / "release_check.json"
    work = Path(tempfile.mkdtemp(prefix="babarify-release-check-"))
    target = work / "Babarify Frame"
    profile = work / "profile"
    env = clean_env(profile)
    results: dict[str, object] = {}
    mp4_before = reg_value(r"Software\Classes\.mp4", "")

    # 1. Fresh install of the older version, with "Open with".
    results["install_old"] = install(old_setup, target, work / "install-old.log", "openwith")
    app = target / "Babarify Frame.exe"
    results["installed_version_old"] = file_version(app)
    results["openwith_registered"] = (
        reg_value(r"Software\Classes\.mp4\OpenWithProgids", "BabarifyFrame.Media") is not None
    )
    results["default_app_unchanged"] = reg_value(r"Software\Classes\.mp4", "") == mp4_before
    results["install_size_mb"] = round(sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) / 1e6)

    # 2. Clean-environment playback; user data is created in the clean profile.
    results["run_old"] = run_app(app, env, MEDIA)
    settings = profile / "APPDATA" / "Babarify" / "Frame" / "settings.json"
    marker = profile / "APPDATA" / "Babarify" / "Frame" / "release-check-marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("user data", encoding="utf-8")

    # 3. The packaged AI worker (needs a model; uses the development models if present).
    models = ROOT / ".models" / "faster-whisper-tiny"
    if models.is_dir():
        wav, _ = make_speech(work / "speech")
        done = subprocess.run(
            [str(target / "ai" / "babarify-ai-worker.exe"), "--media", str(wav), "--model-dir", str(models),
             "--srt", str(work / "s.srt"), "--cues", str(work / "c.json")],
            capture_output=True, text=True, env=env, timeout=600,
        )  # fmt: skip
        lines = [json.loads(x) for x in done.stdout.splitlines() if x.startswith("{")]
        results["ai_worker"] = {
            "exit": done.returncode,
            "done": next((m["done"] for m in lines if "done" in m), None),
            "error": next((m["error"] for m in lines if "error" in m), None),
        }

    # 4. Upgrade, then roll back to the older version.
    results["upgrade"] = install(new_setup, target, work / "install-new.log")
    results["installed_version_new"] = file_version(app)
    results["run_new"] = run_app(app, env, MEDIA)
    results["data_kept_after_upgrade"] = marker.is_file() and settings.is_file()
    results["rollback"] = install(old_setup, target, work / "install-rollback.log")
    results["installed_version_after_rollback"] = file_version(app)
    results["run_rollback"] = run_app(app, env, MEDIA)
    results["data_kept_after_rollback"] = marker.is_file() and settings.is_file()

    # 5. Silent uninstall: program and registry entries gone, user data kept.
    uninstaller = next(target.glob("unins*.exe"))
    results["uninstall"] = subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES"], timeout=600
    ).returncode
    time.sleep(3)  # the uninstaller finishes from a temporary copy
    results["program_removed"] = not app.exists() and not (target / "_internal").exists()
    results["uninstall_entry_removed"] = reg_value(UNINSTALL_KEY, "DisplayName") is None
    results["openwith_removed"] = (
        reg_value(r"Software\Classes\.mp4\OpenWithProgids", "BabarifyFrame.Media") is None
    )
    results["default_app_still_unchanged"] = reg_value(r"Software\Classes\.mp4", "") == mp4_before
    results["user_data_kept_on_silent_uninstall"] = marker.is_file()
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
