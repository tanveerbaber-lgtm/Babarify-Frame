# M5 Acceptance Report — Audio and Subtitle Studio

**Date:** 2026-10-31 · **Engine:** libVLC 3.0.24 x64 (mpv checked as the alternate engine) ·
**Machine:** i7-8565U, Intel UHD 620, Windows 11, 3840×2160 @ 250 % ·
**Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **CONDITIONAL** — accepted by the owner on 2026-10-31

All M5 deliverables are implemented and covered by automated tests on the selected engine.
At the owner's request this milestone was finished on a **lean track**: the planned
pixel-level render check (`tools/subtitle_render_check.py`) and the screenshot pass were
not done. As a result, what libVLC actually draws on screen (subtitle colour, size, position
and delay timing) rests on the measurements from the M5 spike, not on a check that has been
committed and can be re-run. That is the only reason for CONDITIONAL rather than PASS.

## Acceptance criteria (plan §8, M5)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Track changes work on verified samples | **PASS** | `s_black_tracks_720p.mkv` (2 audio + 2 embedded SRT, eng/fra, ffprobe-verified): listing, audio switch, subtitle select and Off pass on libVLC and on mpv (`tests/integration/test_audio_subtitles_engine.py`). External files load and are selected for SRT, WebVTT, ASS, MicroDVD, cp1252 SRT and UTF-8-BOM SRT; the sidecar `.srt` is detected. |
| A2 | Sync controls have clear units and reset | **PASS** | Delays are integer **ms**, **positive = later**, stated in the Sync dialog tooltips and captions and in every status message ("Subtitle delay: +100 ms"). Each delay has its own Reset button; delays reset when another file is opened; the value is clamped to ±60 s. Covered by the UI tests and `test_delays_are_applied_and_reset`. |
| A3 | Subtitle settings persist | **PASS** | Settings → *Subtitles and audio*: show automatically, subtitle and audio language, font (installed fonts only), size, colour, background, position. Round trip through `settings.json` is tested, and bad values in the file fall back to defaults. A style change applies live on mpv; on libVLC it restarts the engine and keeps position, play state, selected tracks and delays (`test_restart_style_engine_keeps_position_tracks_and_delays`). |
| A4 | Limitations are disclosed | **PASS** | On the Settings card: ASS/SSA keep their own styling; libVLC restarts playback for a style change; dual subtitles are not available. A missing saved font is flagged as "(not installed)" with a warning, because libVLC silently falls back to its default font. Capabilities report `supports_dual_subtitles=False` and how the style applies (`subtitle_style`). |
| A5 | Nothing is uploaded without explicit action | **PASS** | Subtitle files are read only when the user chooses or drops one. The path is validated locally (control characters, existence, extension allow-list, 20 MB limit) and handed to the local engine. No network code was added. Remote URIs stay rejected by the M2 rules. |

### Deliverables

| Deliverable | Status |
|---|---|
| Audio track selection | ✅ Subtitles button in the control bar, *Audio & Subtitles* menu, **B** cycles audio |
| Subtitle track selection and external loading | ✅ Same menu with Off; **V** cycles subtitles; *Load subtitle file…* (Ctrl+Shift+O, opens in the video's folder); drop a subtitle file onto a playing video |
| Subtitle and audio delay | ✅ Sync dialog (Ctrl+D) with ±50 ms buttons and Reset; **G/H** subtitles, **J/K** audio |
| Font, size, colour, background, position | ✅ Settings card; plain-text subtitles only (ASS keeps its authored styling) |
| Clear behaviour for missing fonts, unsupported formats, unavailable tracks | ✅ Missing font flagged; an unknown extension gives "…not supported: subtitle format '.xyz'"; a missing file gives "The file could not be found: name"; an unreadable or empty file gives a status-bar notice while playback continues; track controls are disabled when there is no media |
| Dual subtitles only if reliable | ⏸ Not offered; disclosed (see §3) |

## 1. Test results

| Suite | Result |
|---|---|
| Unit (contract, mock, styles): `tests/unit/test_audio_subtitles.py` | 26 tests |
| UI (mock engine): `tests/ui/test_tracks_ui.py` | 36 tests |
| Real engine: `tests/integration/test_audio_subtitles_engine.py` | libVLC **15/15 passed**, 3 consecutive runs; mpv 7 key tests passed (one process each, see S1) |
| Full default suite | **284 passed**, 72 skipped (opt-in mpv runs), 0 failed |
| Unit + UI | 202 passed, 3 consecutive runs |
| ruff and strict mypy | clean (33 source files) |

New fixtures (14 files, subtitle set) are listed in the [test corpus](../../testing/test-corpus.md).

## 2. Defects found and fixed

| ID | Defect | Fix |
|---|---|---|
| R23 | A newly selected libVLC subtitle track, or a new subtitle delay, missed the lines libVLC had already read ahead | Re-seek to the current time after the change |
| R24 | libVLC `add_slave` reports success for a broken file, so no track appears and there is no error | Wait up to 2.5 s for a new track; otherwise emit a `Notice` |
| R22 | Intermittent "C++ object already deleted" error from the M4 Playback info Copy button, whose label-reset timer outlived the dialog | Timer bound to the button |

## 3. Limitations and open items

1. **No committed render check (reason for CONDITIONAL).** Style mappings for libVLC
   (`--freetype-rel-fontsize`, `--freetype-color`, `--freetype-background-opacity`,
   `--sub-margin`) and the effect of delays were measured from screen pixels in the spike, but
   that measurement was not turned into a committed, re-runnable tool. The mpv style mapping
   (`sub-font-size`, `sub-color`, `sub-back-color`, `sub-pos`) has only been checked at the
   API level. Proposed follow-up: `tools/subtitle_render_check.py`, with the screenshot
   ownership checks from R16.
2. **Dual subtitles not offered.** libVLC 3 renders one subtitle track at a time. mpv has
   `secondary-sid`, but it is unverified and mpv is not the shipped engine.
3. **libVLC style change restarts the engine.** Position, play state, selected tracks and
   delays come back. Of several loaded external subtitle files, only the selected one is
   reloaded; the others must be loaded again.
4. **Style applies to plain-text subtitles only.** ASS/SSA and image subtitles (VobSub `.idx`)
   keep their own look.
5. **Preferred languages** match ISO 639-2 codes and common aliases (fra/fre, deu/ger, en…).
   Tracks without a language tag are never matched; with *Show subtitles automatically* on,
   the first track is used when no track matches.
6. **Carried forward:** mpv multi-instance crash S1 (mpv tests stay opt-in, one engine per
   process); the M3 large-resize stall R19.

## 4. Changes in this milestone

- Contract and models: track, external subtitle, delay and style API; `Notice` event;
  `SubtitleStyle`, `SubtitlePosition`, `SUBTITLE_EXTENSIONS`; new capability fields
  ([architecture overview](../../architecture/overview.md#audio-and-subtitles-m5)).
- Adapters: libVLC (re-seek, add-slave confirmation, per-style shared instance), mpv (live style),
  and mock.
- UI: `ui/subtitles.py` (track labels, tracks menu, Sync dialog), control-bar button, menus and
  shortcuts, drag-and-drop, the Settings card, track preferences applied once per file.
- Preferences: `subtitles_auto`, `preferred_audio_language`, `preferred_subtitle_language`,
  `subtitle_style`, all validated on load.
