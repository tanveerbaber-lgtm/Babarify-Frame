# Babarify Frame

**Every Frame, Better.** A free, privacy-focused media player by Babarify.

> Status: **Milestone 3 — Premium UI Foundation** (awaiting acceptance). The app plays
> local video and audio files in a branded interface with Home, Now Playing and Settings
> pages, fullscreen with auto-hiding controls, and saved preferences. See
> [the plan](Babarify_Vision_Official_Architecture_and_Milestones.md) and the milestone
> reports for [M1](docs/milestones/M1/), [M2](docs/milestones/M2/) and [M3](docs/milestones/M3/).

- No ads, no account, no telemetry by default.
- First platform: Windows 10/11 64-bit. Android and iOS come after dedicated feasibility milestones.
- Playback engine: **libVLC** (provisional, [ADR-0001](docs/decisions/ADR-0001-playback-engine.md));
  mpv is kept as a maintained alternative.

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
.\.venv\Scripts\python.exe -m babarify_frame [FILE] [--engine libvlc|mpv]
```

Open files with **Ctrl+O**, by dragging them onto the window, or as a command-line argument.

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | Seek back / forward (step set in Settings, default 10 s) |
| ↑ / ↓ | Volume up / down |
| M | Mute |
| S | Stop |
| F, F11, double-click video | Fullscreen (Esc to leave) |
| Ctrl+1 / 2 / 3 | Home / Now Playing / Settings |
| Ctrl+O / Ctrl+Q | Open / exit |
| F1 | Keyboard shortcuts |

Playback keys act on the Now Playing page. Preferences (volume, window size, seek step,
fullscreen behaviour) are stored only on this PC in `%APPDATA%\Babarify\Frame\settings.json`
(override the folder with `BABARIFY_CONFIG_DIR`).

`--smoke-test [MS]` opens the window (and FILE), then exits after MS milliseconds (used by tests).

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Integration tests skip automatically when an engine library or the generated media is
missing (generate it with `tools\engine-benchmark\make_media.py`). mpv tests are opt-in:
set `BABARIFY_TEST_MPV=1` (see M1 finding S1). Resource stress tests run separately:

```powershell
.\.venv\Scripts\python.exe -m pytest -m stress -s
```

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
  configuration/ typed preferences + local JSON store
  ui/          PySide6 shell (main_window), pages (home, player, settings), controls, theme tokens
tests/         unit, integration, ui, stress
tools/         engine-benchmark, player_screenshot, ui_responsiveness, real_input_check
branding/      icon source and generator
docs/          architecture, decisions (ADRs), milestone reports
```

## License

Not chosen yet — tracked as an open decision in the
[M1 licensing report](docs/milestones/M1/licensing-report.md). Until a license
is added, all rights are reserved.
