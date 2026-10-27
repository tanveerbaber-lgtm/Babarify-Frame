# M1 Environment Report

**Date:** 2026-10-27 · **Repository:** https://github.com/tanveerbaber-lgtm/Babarify-Frame (branch `main`)
**Prepared by:** Claude (Claude Code), for Tanveer Baber

## Repository state before M1

- Commit `a477120` ("Initial commit: Babarify Frame plan and app icon"): plan document,
  `branding/` (icon source, generated icons, generator script), two branding reference
  images in the root, `.gitignore`.
- No source code existed. Nothing was deleted, moved or reset during M1. The plan
  document's filename still says "Vision"; it was left unchanged on purpose.

## Machine

| Item | Value | How verified |
|---|---|---|
| OS | Windows 11 Home, 10.0.26300, 64-bit | `Win32_OperatingSystem` |
| CPU | Intel Core i7-8565U @ 1.80 GHz, 4 cores / 8 threads (laptop, Whiskey Lake) | `Win32_Processor` |
| RAM | 31.7 GB | `Win32_ComputerSystem` |
| GPU 1 | Intel UHD Graphics 620, driver 31.0.101.2145 (2026-09-02) — drives the display | `Win32_VideoController` |
| GPU 2 | NVIDIA GeForce MX150, driver 32.0.15.8183 (2025-11-04) — hybrid/Optimus, no display attached | `Win32_VideoController` |
| Display | 3840 × 2160 @ 60 Hz on the Intel GPU | `Win32_VideoController` |
| Power during benchmark | On AC power, battery 100 %, Windows power plan *Balanced* | `psutil.sensors_battery`, `powercfg` (recorded by bench.py) |

## Tools

| Tool | Version | Notes |
|---|---|---|
| Python | 3.13.15 (x64) — used | `py -0p` also lists 3.14 at `C:\Python314`; not used |
| Git | 2.55.0.windows.3 | |
| GitHub CLI | present | used to look up the libmpv release |
| FFmpeg / ffprobe | 9.0.2 `full_build-www.gyan.dev` (`--enable-gpl --enable-version3`) | **dev-only**: generates synthetic test media; never distributed |
| winget, Chocolatey | present | winget used once (failed, see below) |
| mpv / vlc on PATH | not present | |

## Python environment

Project virtual environment `.venv` (git-ignored), created with `py -3.13 -m venv .venv`,
package installed editable with `pip install -e .`. Exact versions:

| Package | Version | Role |
|---|---|---|
| PySide6 (+ Essentials, Addons, shiboken6) | 6.12.0 | UI. Runtime needs only PySide6-Essentials; the full meta-package was installed for development convenience |
| python-vlc | 3.0.21203 | libVLC binding (prototype) |
| mpv (python-mpv) | 1.0.8 | libmpv binding (prototype) |
| psutil | 7.2.2 | benchmark CPU/memory |
| pytest / pytest-qt | 9.1.1 / 4.5.0 | tests |
| ruff | 0.17.3 | lint + format |
| mypy | 2.4.0 | type checks (strict) |
| pip-licenses | 5.5.5 | license inventory |
| py-spy | 0.4.2 | stack dumps of hung test processes (diagnosis only) |

A separate scratch virtual environment (outside the repo) with Pillow 11.3.0 was used
only to build the icon set.

## Playback engines

| Engine | What was found | What was used |
|---|---|---|
| libVLC | VLC 3.0.24 installed in `C:\Program Files (x86)\VideoLAN\VLC` — **32-bit** (`libvlc.dll` PE machine `0x14C`), cannot load in 64-bit Python | Official `vlc-3.0.24-win64.zip` from `download.videolan.org`, SHA-256 `fcf30850…a1ca6323` **matches** VideoLAN's published `.sha256`. Extracted to `.engines/vlc/vlc-3.0.24/`. libVLC reports `3.0.24 Vetinari`; 360 plugin DLLs |
| libmpv | Not installed | `mpv-dev-x86_64-20261021-git-e471496c56.7z` from the shinchiro/mpv-winbuild-cmake GitHub release `20261021` (the Windows builds linked from mpv.io). SHA-256 `efc719ef…9ea633` **matches** GitHub's recorded asset digest. Extracted to `.engines/mpv/` (`libmpv-2.dll`, 121 MB). Reports `mpv v0.41.0-1227-ge471496c5`, FFmpeg `N-127893-g9a861e968` |

Notes:

- `winget install VideoLAN.VLC --architecture x64` failed (exit 43): winget treated the
  existing 32-bit install as the same package and found no upgrade. Rather than force an
  install that could replace the user's VLC, the portable zip was used. **The existing
  32-bit VLC was not modified.**
- No engine files were installed system-wide; nothing outside the repository changed
  except the scratch icon venv and Python's pip cache.
- The shinchiro build is a third-party build referenced by mpv.io, not an mpv-project
  release. Its provenance is adequate for evaluation, not automatically for distribution
  (see licensing report).

## Hardware decoding observed

Both engines selected **D3D11VA on the Intel UHD Graphics 620** (the display GPU) for
H.264, HEVC (8-bit) and VP9. **AV1 was decoded in software by both engines**: the UHD 620
has no AV1 decode hardware (libVLC logged no hardware decoder; mpv reported
`hwdec-current = no`). The NVIDIA MX150 was not used by either engine with default
settings. Details: [benchmark report](benchmark-report.md).

## Reproducing this environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
# engines: see README "Engine libraries"
.\.venv\Scripts\python.exe tools\engine-benchmark\make_media.py
```

## Known environment limitations

- One machine only: a 2018-era 4-core laptop with an Intel iGPU. Results do not
  represent desktops, AMD/NVIDIA display GPUs, Windows 10, or HDR displays.
- Screen-scaling: the display uses 4K at high DPI scaling; no other DPI was tested.
- The machine was in normal use (not an isolated benchmark box).
