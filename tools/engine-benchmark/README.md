# Engine benchmark

Compares libVLC and mpv through the **same** `PlaybackEngine` adapters the app uses,
rendering into a real Qt window.

```powershell
.\.venv\Scripts\python.exe tools\engine-benchmark\make_media.py     # synthetic corpus (needs ffmpeg)
.\.venv\Scripts\python.exe tools\engine-benchmark\bench.py --trials 5
```

| File | Purpose |
|---|---|
| `make_media.py` | Generates synthetic test media (FFmpeg `testsrc2` + -60 dB sine): the benchmark set, the M2 playback corpus (`c_*` files, 19 containers/codecs) and invalid files, plus `media-manifest.json` with commands, expectations and SHA-256 |
| `trial.py` | One scenario, one engine, one fresh process; prints a `RESULT {json}` line |
| `bench.py` | Runs all trials (engine order alternates), records machine info, writes `results/` |
| `results/summary.md`, `summary.json` | Committed evidence for the M1 benchmark report |
| `results/raw/` | Every trial result (git-ignored) |
| `hw_decode_check.py` | M4: decoder reported and CPU per engine × hardware setting × media → `results/hw_decode_check.json` |
| `engine_build_info.py` | Build/version information reported by both engines |
| `mpv_vo_check.py` | mpv dropped frames by video output (M1 follow-up) |

## Scenarios

- **perf** (per media): engine init (DLL load + start), open→PLAYING event,
  open→progress, 8 s steady playback (CPU, RSS, dropped frames), 3 seeks, close time,
  hardware decoder and video output in use, rejected state transitions.
- **tracks**: track list of a file with 2 audio + 2 subtitle tracks.
- **errors**: a text file named `.mp4` and a truncated MP4; then a valid file must play.
- **cycles**: 15 open/play/stop cycles on one engine, then repeated engine create/close.

## Measurement caveats

- Progress-based metrics (`open_to_progress_ms`, `seek_ms`) subtract a fixed 500 ms
  of playback; they are bounded by each engine's position-report interval.
- CPU is per-process (% of one logical core); GPU utilisation is not measured.
- All trials run with a warm OS file cache; true cold start is not measured.
- Results are for one machine; see the report for its specification and power state.
