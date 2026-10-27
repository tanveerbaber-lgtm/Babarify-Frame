# M3 Acceptance Report — Premium UI Foundation

**Date:** 2026-10-27 · **Engine:** libVLC 3.0.24 x64 · **Machine:** same as M1/M2
(i7-8565U, Intel UHD 620, Windows 11, 3840×2160 at 250 % scaling) ·
**Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Proposed decision: **CONDITIONAL**

All M3 deliverables are implemented, and four of the five acceptance criteria pass with
evidence. One criterion is conditional: the UI stays responsive during playback and
typical interaction, but a **large jump in window size** (or leaving fullscreen) blocks
the UI for 70–112 ms on this 4K / 250 % display, just over the 100 ms limit set before
measuring. The cause is Qt's own layout and painting at high DPI, not Python and not
the playback engine (details below). It does not block M4, which owns performance work.

## Acceptance criteria (plan §8, M3)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | UI remains responsive during playback | **CONDITIONAL** | `tools/ui_responsiveness.py` → [`evidence/ui_responsiveness.json`](evidence/ui_responsiveness.json). Passive 4K HEVC playback: p95 2.2 ms, max 3.5 ms. Playback + 12 interactions: p95 2.5 ms (limit 16 ms) ✅; max **111.7 ms** (limit 100 ms) ❌, caused by one 900→1400 px resize. See §1. |
| A2 | Common actions are easy to find | **PASS** | Home page leads with a single primary **Open file…** button and a drop zone ([home](evidence/home.png)); navigation rail; menus list every action with its shortcut; tooltips show keys; **F1** lists all shortcuts. Subjective — owner review recommended. |
| A3 | Keyboard focus and shortcuts behave consistently | **PASS** | One documented model: playback keys act only on Now Playing; Ctrl+O/Q, Ctrl+1/2/3, F1, Esc everywhere. Tests: `test_playback_shortcuts_only_on_player_page`, `test_navigation_by_rail_and_shortcuts`, `test_settings_controls_are_keyboard_reachable`. A visible cyan focus ring is styled for every focusable control. |
| A4 | Window resizing and fullscreen transitions work reliably | **PASS** | Responsive breakpoints tested (`test_control_bar_breakpoints`, minimum size); fullscreen round trip restores maximized state; leaving the page exits fullscreen; **real mouse input over live libVLC video**: double-click in/out of fullscreen, idle auto-hide, mouse-move reveal — all pass (`tools/real_input_check.py`). Screenshots: [narrow](evidence/playing_narrow.png), [fullscreen](evidence/fullscreen_controls.png), [fullscreen idle](evidence/fullscreen_idle.png). |
| A5 | Branding and spacing remain consistent | **PASS** | All colours, spacing (4/8/12/16/24/32 px), radii and type sizes come from `ui/theme.py` tokens. Screenshots of every page and state use the same palette, type scale and components. |

### Deliverables

| Deliverable | Status |
|---|---|
| Main application shell and navigation | ✅ Navigation rail (Home · Now Playing · Settings · About), page stack, menus |
| Video area and playback control layout | ✅ Full-width seek row; accent play button, skip, stop, title, speed, volume, fullscreen |
| Dark theme with blue/cyan and green accents | ✅ Token-based stylesheet; accent gradient for primary actions; green for "on" |
| Responsive resizing and fullscreen transitions | ✅ Breakpoints at 760 / 540 px; fullscreen auto-hide with cursor polling |
| Keyboard shortcuts and accessible control labels | ✅ Shortcut model, F1 list, accessible names on every button/slider (tested) |
| Empty, loading, error and no-media states | ✅ Home (empty), "Opening …" (loading), error page with icon and "Open another file…", "Nothing is playing", audio-only page |
| Basic preferences and persistence | ✅ JSON at `%APPDATA%\Babarify\Frame\settings.json`; validated, atomic, corruption-safe |

## 1. UI responsiveness — measurement and finding

Method: a precise 16 ms Qt timer records how late each tick fires (event-loop lag) while
the real app plays 4K HEVC and the script resizes the window, switches pages, seeks,
pauses and toggles fullscreen. Thresholds were fixed before the first run.

| Scenario | p95 | p99 | max | Result |
|---|---|---|---|---|
| Idle (measurement floor) | 2.1 ms | 2.8 ms | 3.0 ms | — |
| Playing 4K HEVC, no interaction | 2.2 ms | 2.8 ms | 3.5 ms | PASS |
| Playing + 12 interactions | 2.5 ms | 14.9 ms | **111.7 ms** | p95 PASS, max FAIL |

Worst lag per action (final run): resize to 1400×860 **111.7 ms**, exit fullscreen 82.0,
enter fullscreen 36.9, resize to 900×600 26.9, settings page 14.9; seek, play, pause and
the player page all ≤ 3.5 ms.

Investigation (`scratchpad` probes, numbers reproducible with the tools):

- **Not the engine:** the same resize costs 110–126 ms with no media loaded.
- **Not Python:** profiling attributes < 1 ms per resize to Python code.
- **Mostly not the stylesheet:** 105 ms with no stylesheet, 113–124 ms with it.
- **Qt's floor here:** a bare Qt window takes 37 ms for the same resize at 2.5× DPI.
- **GPU-backed widgets made it much worse** (`QT_WIDGETS_RHI=1`: 600–860 ms), so not adopted.

So roughly 37 ms is Qt's own cost at this resolution and ~70 ms comes from laying out and
repainting our widget tree at 3500×2150 physical pixels. Interactive drag-resizing moves
in small steps and is less affected; the measured case is a single large jump.
**Next step (M4):** profile Qt layout/paint (native child-window count, page stack
layout, icon rendering) and re-measure.

## 2. Tests and checks (final code)

| Command | Result |
|---|---|
| `python -m pytest` (unit + UI + libVLC integration) | **167 passed**, 34 skipped (mpv, opt-in), 2 deselected (stress); exit 0 |
| `python tools/real_input_check.py` (real mouse over live video) | 4/4 checks pass |
| `python tools/ui_responsiveness.py` | p95 pass; max fail (see §1) |
| `ruff check .` / `ruff format --check .` | All checks passed / 58 files formatted |
| `mypy` (strict) | No issues in 31 source files |

New tests in M3: 22 preference tests (defaults, round trip, atomic save, clamping of
untrusted values, invalid geometry, corrupt-file quarantine, save failure) and 40+ shell
tests (navigation, shortcut scoping, engine unavailable, pending open, seek step from
preferences, speed menu, error page, fullscreen chrome and maximized restore, auto-hide
timing, start-in-fullscreen, breakpoints, persistence of volume/geometry/settings,
off-screen geometry, accessible names, close order).

## 3. Privacy and safety

- Preferences hold no media paths or history; they stay on the PC; the Settings page
  shows exactly where.
- Tests and tools never touch the user's real settings: every test uses a temporary
  store, subprocess tests set `BABARIFY_CONFIG_DIR`, tools use throw-away folders.
- The screenshot tool and the real-input tool refuse to act unless Windows reports that
  the target pixels belong to the Babarify Frame window. The real-input tool moved the
  cursor briefly and restored it.
- All 8 evidence screenshots were inspected and contain only Babarify Frame and
  synthetic test media.

## 4. Known limitations

- **A1 conditional** — large window-size jumps at 4K / 250 % (above).
- Control-bar buttons are mouse targets and are not in the Tab order; every action is
  reachable by keyboard through shortcuts and menus. A screen-reader pass is not done
  (planned for M11's accessibility review).
- Controls cannot float over the video (Windows draws the engine's native window on
  top), so in fullscreen the bar collapses and the video expands instead of an overlay.
- No recent files on Home: playback history needs M6's privacy controls.
- Tested at one DPI (250 %) on one display; light theme not offered.
- mpv remains opt-in (M1 finding S1).

## 5. Next actions

1. **Owner:** try the new interface (`python -m babarify_frame`), then accept or reject
   M3 as CONDITIONAL.
2. Commit and push M3 (awaiting approval).
3. M4 — Playback Reliability and Performance; includes the A1 resize investigation.
