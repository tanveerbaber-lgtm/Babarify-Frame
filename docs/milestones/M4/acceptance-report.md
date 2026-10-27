# M4 Acceptance Report — Playback Reliability and Performance

**Date:** 2026-10-27 · **Engine:** libVLC 3.0.24 x64 (mpv 0.41-dev measured for comparison) ·
**Machine:** i7-8565U, Intel UHD 620 (display), NVIDIA MX150 (idle), Windows 11, 3840×2160 @ 250 % ·
**Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Proposed decision: **PASS**

All M4 deliverables are implemented and all five acceptance criteria have recorded
evidence. The new tests found four real defects; all four are fixed and guarded by
regression tests, including one that crashed libVLC itself (R20). Two items stay open and
are carried forward: the mpv multi-instance crash (alternate engine, not shipped) and the
M3 large-resize stall (a performance limitation, not a crash).

## Acceptance criteria (plan §8, M4)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Declared test cases have recorded results | **PASS** | 42-file corpus with expectations and checksums ([test-corpus](../../testing/test-corpus.md)); default suite **201 passed** ×2 runs; stress results in §2; per-defect guards in the [regression catalog](../../testing/regressions.md). |
| A2 | Hardware decoding is reported accurately and never falsely promised | **PASS** | 32-run matrix (2 engines × Automatic/Off × 8 media, fresh process each) → [`hw_decode_check.json`](../../../tools/engine-benchmark/results/hw_decode_check.json): "Off" is software in 16/16 runs; "hardware" appears only when the engine confirmed it, and CPU confirms each label (§1). The check caught and fixed R18 ("Off" still used the GPU). |
| A3 | Unsupported capabilities are handled clearly | **PASS** | Codecs this GPU cannot decode (AV1, VP8) are shown as "software"; audio-only shows "no video"; capability reports "disabled" when Off; invalid/empty files give a clear error; the Playback info panel (Ctrl+I) shows decoder, frames, setting, last error and engine log. |
| A4 | No unresolved release-blocking crash or data-corruption defect | **PASS** (selected engine) | libVLC: R20 crash fixed; 2/2 full suites exit 0 (~150 engines per process); shutdown in 8 states + app close while opening all pass; 10-minute session 0 errors. mpv's S1 crash remains open but mpv is not shipped (ADR-0001). |
| A5 | Performance claims are based on reproducible measurements | **PASS** | Every number in this report comes from a committed tool: `hw_decode_check.py`, `tests/stress/*`, `ui_responsiveness.py`, `resize_probe.py`; thresholds fixed before each first run. |

### Deliverables

| Deliverable | Status |
|---|---|
| Expanded test corpus with manifest and checksums | ✅ 16 edge files (VFR, interlaced 1080i, rotation metadata, 4K 10-bit HEVC, 120 fps, 1-hour, MKV without cues, fragmented MP4, mono 8 kHz, 7.1 FLAC, 96 kHz/24-bit, Unicode/`#%`/wrong-extension names, damaged stream, empty file); ffprobe-verified |
| Hardware-decoding capability detection and safe fallback | ✅ `EngineOptions(hardware_decoding)`; Settings → Automatic/Off with restart-and-resume; unsupported codecs fall back to software (observed for AV1, VP8; mpv also for MPEG-2) |
| Diagnostics for codec, resolution, frame rate, decoder, errors | ✅ Playback info panel (Ctrl+I) with Copy; status bar decoder line |
| Long-session, repeated-open, seeking and shutdown tests | ✅ `tests/stress/test_long_session.py`, `test_resource_stability.py`, `tests/integration/test_shutdown.py` |
| CPU and memory measurements under defined conditions | ✅ §1 and §2 |
| Regression tests for previously discovered failures | ✅ [regression catalog](../../testing/regressions.md): R1–R21, each mapped to its guard |

## 1. Hardware decoding — truthfulness and CPU

Fresh process per row, 1280×720 window, 1.5 s settle, 5 s measurement; CPU = % of one core.

| Media | libVLC Auto | libVLC Off | mpv Auto | mpv Off |
|---|---|---|---|---|
| H.264 1080p | hardware (D3D11VA), 3 % | software, 28 % | hardware, 11 % | software, 22 % |
| HEVC 2160p | hardware, 8 % | software, 82 % | hardware, 13 % (11 dropped) | software, 158 % (22 dropped) |
| HEVC 10-bit 2160p | hardware, 5 % | software, **131 %** | hardware, 9 % (20 dropped) | software, 183 % (40 dropped) |
| VP9 1080p | hardware, 9 % | software, 23 % | hardware, 13 % | software, 23 % |
| MPEG-2 576p | hardware, 8 % | software, 8 % | **software** (mpv `auto-safe` excludes MPEG-2), 7 % | software, 10 % |
| AV1 1080p | **software** (no AV1 hardware on UHD 620), 34 % | software, 36 % | software, 32 % | software, 46 % |
| VP8 720p | **software**, 13 % | software, 15 % | software, 11 % | software, 10 % |
| FLAC audio | no video, 4 % | no video, 4 % | no video, 4 % | no video, 3 % |

libVLC dropped no frames in any run; mpv drops frames on 4K HEVC (renderer, M1 finding).

## 2. Reliability (thresholds fixed before the first run)

| Test | Threshold | Result |
|---|---|---|
| 10-minute continuous playback (1-hour file) | drift ≤ 2 %; after 2-min warm-up RSS ≤ +64 MB, handles ≤ +300, threads ≤ +4; 0 errors | drift **−0.02 %**, RSS **+0.6 MB**, handles −17, threads −2, **0 errors**, 12,011 frames shown, **0 dropped** — PASS |
| Seek storm: 300 seeded random seeks over 5 files (4K HEVC, MKV without cues, fragmented MP4, 1-hour, H.264), play/pause mixed | 0 timeouts (5 s), 0 errors; playing seeks must *resume* (position moves past target) | **0 timeouts, 0 errors**; resume p50 524 ms, p95 986 ms, max 1.9 s — PASS (after fixing R21; first run had 24 timeouts) |
| 60 opens on one engine | RSS ≤ +64 MB, threads ≤ +4, handles ≤ +300 | −390 MB*, −18, −179 — PASS |
| 50 engine create/close cycles | same | handles **+45**, RSS −180 MB*, threads −3 — PASS (before R20 fix: handles +757, RSS +60 MB — FAIL) |
| Shutdown in 8 states (loading, playing, paused, mid-seek, ended, error, stopped, after a seek burst) | `close()` < 5 s | 8/8 PASS |
| Real app closed while opening a 4K file (150 / 600 ms) | exit 0 | 2/2 PASS |

\* Negative RSS growth is Windows trimming the working set; growth is what the threshold limits.

## 3. Defects found by M4 tests (all fixed)

| ID | Found by | Defect | Fix |
|---|---|---|---|
| R18 | `hw_decode_check.py` | Hardware decoding "Off" kept using the GPU in libVLC | libVLC 3.0.24 ignores `--avcodec-hw` at instance level → per-media `:avcodec-hw=` option |
| R20 | 50-cycle stress, then a full-suite crash | Each libVLC instance leaked ~15 handles / 0.5 MB; after ~100 instances `libvlc_new` crashed | Reproduced with bare libVLC (no Babarify code) → one shared libVLC instance per process |
| R21 | Seek storm | A seek just after pause left the displayed position stale | Always report the accepted seek target |
| — | UI test | Changing the hardware setting would have navigated away from Settings | Restart path no longer signals engine failure |

## 4. Carried forward

- **R19 — large resize stall (M3 A1).** Investigated with `tools/resize_probe.py`
  (grow 900×600 → 1400×860, median of 8): bare Qt 34 ms; full app 110 ms; without native
  video window 105; without navigation rail 94; without menu/status bar 93; narrowed
  stylesheet rule 110. The cost is spread across the whole widget tree at 2.5× DPI with no
  single dominant part, so there is no cheap targeted fix. Normal interaction is unaffected
  (seek, play/pause ≤ 4 ms). Revisit with a Qt-level profile if users report it.
- **R7 / S1 — mpv multi-instance crash.** Unchanged; mpv tests opt-in.
- **Shared libVLC log stream:** with several engines alive at once their diagnostics can mix
  (only tests do that; the app runs one engine).
- Single test machine; no AMD/NVIDIA display GPU; Windows 10 untested; HDR not tested and
  not claimed.

## 5. Commands (final code)

| Command | Result |
|---|---|
| `python -m pytest` | **201 passed**, 54 skipped (mpv opt-in), 4 deselected (stress); exit 0, twice |
| `BABARIFY_ENGINE_CYCLES=50 python -m pytest tests/stress/test_resource_stability.py -m stress -s` | 2 passed |
| `python -m pytest tests/stress/test_long_session.py -m stress -s` | long session PASS (10 min); seek storm PASS |
| `python tools/engine-benchmark/hw_decode_check.py` | 32/32 runs; "Off always reported as software: True" |
| `ruff check .` / `ruff format --check .` / `mypy` (strict) | clean / 66 files formatted / no issues in 32 files |

## 6. Next actions

1. **Owner:** accept or reject M4 as PASS.
2. Commit and push M4 (awaiting approval).
3. M5 — Audio and Subtitle Studio.
