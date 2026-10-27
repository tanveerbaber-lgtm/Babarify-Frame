# M1 Acceptance Report — Feasibility and Architecture

**Date:** 2026-10-27 · **Branch:** `main` (uncommitted at time of writing) ·
**Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **CONDITIONAL** — accepted by the owner on 2026-10-27

The owner also accepted ADR-0001 (libVLC, provisional). M2 may start.

Every M1 deliverable exists and every acceptance criterion has evidence. M1 is
conditional, not a clean PASS, because the engine choice in ADR-0001 is a *provisional*
recommendation that needs the owner's acceptance, and two of its supporting questions
(mpv crash S1, second-machine results) are still open. Nothing in M2 depends on the
open licensing questions until distribution (M10).

## Acceptance criteria (plan §8, M1)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Reproducible setup instructions | **PASS** | `README.md` (venv, editable install, engine layout with sources + checksums); [environment report](environment-report.md). Engines are a manual download (documented), not pip-installable. |
| A2 | Shell launches and closes cleanly | **PASS** | `python -m babarify_frame --smoke-test 3000` → exit 0, "exited cleanly with code 0"; UI test `test_app_starts_and_exits_cleanly` passes; screenshot [`evidence/shell.png`](evidence/shell.png) shows branding and both engines loaded. |
| A3 | Mock adapter and contract tests pass | **PASS** | 68 unit tests pass (lifecycle rules, command validation, URI validation incl. rejected network schemes, volume/rate/seek bounds, error mapping, events, unsubscribe, failing listeners, idempotent close, close after error, controller engine switching, factory failure mapping). |
| A4 | Actual benchmark data or documented blockers | **PASS** | 5-trial benchmark, 40/40 perf trials completed, plus tracks/errors/cycles scenarios and follow-ups: [benchmark report](benchmark-report.md). No figures were estimated. |
| A5 | Licensing risks and unknowns recorded | **PASS** (preliminary) | [licensing report](licensing-report.md): verified vs assumed vs open items; libdvdcss in VLC DVD plugins; both engine builds GPL; no legal clearance claimed; no binary published. |
| A6 | No unrelated user changes discarded | **PASS** | `git status`: only additions plus two intended edits (`.gitignore` additions; `branding/generate_icon.py` now also copies icons into app resources — regenerated icons are byte-identical). The plan document, root branding images and the user's 32-bit VLC install are untouched. |
| A7 | Each criterion marked PASS / CONDITIONAL / FAIL / BLOCKED | **PASS** | This table. |
| D1 | Common playback contract, typed models, mock adapter | **PASS** | `playback/contracts.py`, `core/`, `adapters/mock.py`; [architecture overview](../../architecture/overview.md). |
| D2 | Separate engine prototypes and benchmark harness | **PASS** | `adapters/libvlc.py`, `adapters/mpv.py`; `tools/engine-benchmark/`. |
| D3 | Unit tests, static checks | **PASS** | ruff check + format, mypy `--strict`: clean. |
| D4 | Integration/smoke tests where feasible | **PASS for libVLC / FAIL for mpv stability** | libVLC: 10 consecutive runs, 7/7 tests, exit 0. mpv: 7/7 tests pass in-process, but every multi-instance test process ends in an access violation (finding S1). This is an engine finding, not a gap in M1 work. |
| D5 | ADR selects an engine only if evidence is sufficient | **CONDITIONAL** | [ADR-0001](../../decisions/ADR-0001-playback-engine.md): provisional libVLC, explicit conditions and next tests N1–N5. |

## Commands run (final code) and results

| Command | Result |
|---|---|
| `python -m pytest tests/unit tests/ui -q` | **75 passed** (68 unit + 7 UI), 0 failed, 0 skipped |
| `python -m pytest -k "not mpv"` (unit + UI + libVLC integration, one process) | **82 passed**, 7 deselected, exit code 0 |
| `python -m pytest tests/integration -k libvlc` ×10 | **7 passed** each run, exit code 0 every run |
| `python -m pytest tests/integration -k mpv` ×4 (exit code checked) | 7 passed in 3 runs, 1 run died during the first test; **all 4 processes exited 0xC0000005** |
| `python -m ruff check .` / `ruff format --check .` | All checks passed / 42 files already formatted |
| `python -m mypy` (strict) | Success: no issues found in 23 source files |
| `python -m babarify_frame --smoke-test 3000` | exit 0 |
| `tools/engine-benchmark/bench.py --trials 5` | completed; summary committed under `tools/engine-benchmark/results/` |

The full `pytest` run (all 89 tests in one process) is **not** reported as passing.
On the final code, ×2: run 1 — **89 passed**, then the process exited with access
violation 0xC0000005; run 2 — the process crashed mid-run. Both are mpv finding S1
(mpv integration tests share the process). Run the suites separately as listed above,
or deselect mpv (`-k "not mpv"`) for a clean exit.

## Headline benchmark results (median of 5)

- Both engines hardware-decode H.264, HEVC and VP9 via D3D11VA on the Intel UHD 620;
  AV1 is software-decoded by both.
- Open→progress ≈ 0.6–0.85 s for both; mpv seeks resume faster (43–404 ms vs 279–517 ms)
  and initialises faster (90 vs 499 ms).
- 4K HEVC: libVLC 0 dropped frames, 924 MB RSS; mpv 37 dropped / 8 s (renderer-side),
  468 MB RSS.
- CPU 8–12 % of one core for hardware-decoded media on both; ~31 % for AV1.

## Issues found and fixed during M1

| Issue | Fix |
|---|---|
| `play()` after `stop()` broke the lifecycle (READY→PLAYING) | `EngineBase.play()` reloads the selected media |
| Deferred engine calls could run against a released handle (both adapters) | Shared worker in `EngineBase`, drained before adapter teardown |
| libVLC log callback captured nothing (python-vlc `libvlc_log_get_context` signature) | Context lookup removed; HW decoder and video output now detected |
| libVLC reported bad files as played-to-end | Adapter maps "ended, nothing decoded" to `MEDIA_OPEN_FAILED` |
| libVLC no position update when seeking while paused | Adapter reports accepted target |
| Deadlock destroying host window under a live libVLC output | Close engine first; detach log callback first; rule documented |
| Benchmark metrics not comparable between engines | Progress-based metrics added; raw engine values kept for reference |

## Known limitations and open items

1. **S1 — mpv multi-instance access violation**, root cause not isolated (ADR N2).
2. One test machine only (ADR N3).
3. Prototype gaps (libVLC): no seek after end of media; brief PLAYING before open failures.
4. RSS growth over 15 open/stop cycles (both engines) is inconclusive; long-session tests are M4.
5. Project license not chosen (owner: "decide later"); legal review items L2–L5 open.
6. Two libVLC adapter tweaks were made after the final benchmark run (see benchmark report §8).
7. `PySide6` full meta-package installed for development; only `PySide6-Essentials` is a runtime dependency.
8. M2 must implement "close the engine before its host window" in the real main window.

## Recommended next actions

1. **Owner:** accept or reject ADR-0001's provisional libVLC choice (N1), and accept or
   reject M1 as CONDITIONAL.
2. Commit M1 to `main` and push (awaiting owner approval).
3. Optionally, before or alongside M2: the ½-day mpv S1 investigation (N2) and a
   second-machine benchmark run (N3).
4. Update the plan's milestone tracker only after the owner reviews this report.
