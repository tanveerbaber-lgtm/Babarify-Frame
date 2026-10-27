# Babarify Frame

**Every Frame, Better.** A free, privacy-focused media player by Babarify.

> Status: **Milestone 1 — Feasibility and Architecture.** The app opens a branded
> shell and reports which playback engines it can load. It does not play media
> yet; real playback is M2. See [the plan](Babarify_Vision_Official_Architecture_and_Milestones.md)
> and [M1 reports](docs/milestones/M1/).

- No ads, no account, no telemetry by default.
- First platform: Windows 10/11 64-bit. Android and iOS come after dedicated feasibility milestones.
- Playback engine: **not selected yet** — libVLC and mpv are being compared
  ([ADR-0001](docs/decisions/ADR-0001-playback-engine.md)).

## Development setup (Windows)

Requirements: Windows 10/11 x64, Python 3.13 (x64), Git. FFmpeg on `PATH` is only
needed to regenerate benchmark media.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### Engine libraries (development only)

The engines are native libraries and are not installed by pip. Put 64-bit builds in
the git-ignored `.engines/` folder (or point `BABARIFY_VLC_DIR` / `BABARIFY_MPV_DIR` at them):

| Engine | Source used in M1 | Expected layout |
|---|---|---|
| libVLC 3.0.24 x64 | `vlc-3.0.24-win64.zip` from download.videolan.org (SHA-256 verified) | `.engines/vlc/vlc-3.0.24/libvlc.dll` + `plugins/` |
| libmpv | `mpv-dev-x86_64-20261021-git-e471496c56.7z` from shinchiro/mpv-winbuild-cmake (linked from mpv.io; GitHub digest verified) | `.engines/mpv/libmpv-2.dll` |

A 32-bit VLC installation cannot be used from 64-bit Python.

## Run

```powershell
.\.venv\Scripts\python.exe -m babarify_frame
```

`--smoke-test` opens the window, waits briefly and exits with code 0 (used by tests).

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Integration tests skip automatically when an engine library is missing.

## Engine benchmark

```powershell
.\.venv\Scripts\python.exe tools\engine-benchmark\make_media.py
.\.venv\Scripts\python.exe tools\engine-benchmark\bench.py --trials 5
```

See [tools/engine-benchmark/README.md](tools/engine-benchmark/README.md).

## Layout

```text
src/babarify_frame/
  core/        typed models, errors, events (no engine or UI imports)
  playback/    contract, lifecycle rules, factory, controller
    adapters/  mock, libvlc (prototype), mpv (prototype) — the only place engine bindings are imported
  ui/          PySide6 shell
tests/         unit, integration, ui
tools/         engine-benchmark
branding/      icon source and generator
docs/          architecture, decisions (ADRs), milestone reports
```

## License

Not chosen yet — tracked as an open decision in the
[M1 licensing report](docs/milestones/M1/licensing-report.md). Until a license
is added, all rights are reserved.
