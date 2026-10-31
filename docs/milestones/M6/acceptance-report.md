# M6 Acceptance Report — Media Library and Personal History

**Date:** 2026-10-31 · **Engine:** libVLC 3.0.24 x64 ·
**Machine:** i7-8565U, Intel UHD 620, Windows 11, 3840×2160 @ 250 % ·
**Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **PASS** — accepted by the owner on 2026-10-31

All seven deliverables are implemented, and all six acceptance criteria have recorded,
repeatable evidence. The new tests found five real defects (R25–R29). All five are fixed and
guarded by tests, including one that would have crashed start-up on a damaged database.

## Acceptance criteria (plan §8, M6)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Library scanning does not freeze playback or the UI | **PASS** | Scanning and metadata run on one background worker (`LibraryService`); the UI thread only runs short queries. While 2,000 files were scanned and probed, the longest gap of a 10 ms UI timer was 106–124 ms over four runs (threshold 250 ms; `test_scanning_keeps_the_ui_responsive`). Probing waits 0.5 s between files while a video plays, and decodes in software on its own libVLC instance. |
| A2 | Duplicate and unavailable files are handled predictably | **PASS** | Same path under any spelling → one entry (`path_key`). Same content in several places → every copy stays, labelled *Duplicate*, and the tooltip lists the other copies. A deleted or moved file → kept and greyed as *Not found*, never removed silently; *Remove unavailable* removes only records. An unreachable folder (e.g. an unplugged drive) → its entries become unavailable and return when it is back. A cancelled scan marks nothing missing. Covered by `test_rescan_marks_missing_and_reprobes_changed`, `test_unreachable_folder_marks_its_media_unavailable`, `test_duplicates_are_detected_and_both_kept`, `test_cancelled_scan_marks_nothing_missing` and the UI tests. |
| A3 | Resume positions are accurate within a documented tolerance | **PASS** | Tolerance: **±1 s** after a normal pause, stop, file change or close. After a crash the saved point is at most 5 s old. Measured with real libVLC playback of a 1-hour file, closing and reopening the app: the error was **−10 ms** at 1.5 min, 30 min and 55 min, 12 of 12 runs (`test_resume_is_accurate_across_app_restarts`). Rules: at least 10 s watched; finished when less than max(15 s, 3 %) remains; finished files start from the beginning; *Home* (key) starts over. |
| A4 | Database migrations and recovery tests pass | **PASS** | Schema v1 → v2 migration keeps data; a failing migration rolls back completely; a non-database file and a file with overwritten pages are both moved aside (`library.corrupt-<time>.db`) and replaced, and the user is told; a database from a newer version is left byte-for-byte untouched. 30 tests in `tests/unit/test_library_db.py`. |
| A5 | Users can choose which folders are scanned | **PASS** | Only folders added in *Library → Folders…*, *File → Add folder to library…* or by dropping a folder are scanned. Nested duplicates are refused; adding a parent folder takes over its children. Removing a folder removes its records only. Hidden and system folders, symbolic links and junctions are skipped, and only media extensions are added. |
| A6 | Local library use works offline | **PASS** | No network code was added. The library, history, playlists and thumbnails live in `%APPDATA%\Babarify\Frame` (shown in *Settings → Privacy*). All tests run without a network. |

### Deliverables

| Deliverable | Status |
|---|---|
| User-selected library folders | ✅ Folders dialog, *File → Add folder to library…*, drop a folder onto the window |
| Background scanning | ✅ One worker for scan and metadata; *Stop* keeps the work done so far; rescan at start-up picks up changes |
| Search, sort, recently played, playlists | ✅ Search across names and folders (literal `%` and `_`); sort by name, date added, recently played, length, size (remembered); *Recently played* on Home; playlists with create, rename, delete, add, reorder and remove, played in order (**N/P**), with missing items skipped |
| Resume and continue watching | ✅ Automatic resume with "Resumed at mm:ss · Home starts over"; *Continue watching* cards with thumbnail and progress |
| Thumbnails and metadata | ✅ Duration, size and codecs from libVLC preparsing; a 320 px JPEG thumbnail from a muted, windowless decode at 10 % of the file |
| SQLite schema migrations and recovery tests | ✅ §1 and A4 |
| Remove entries and clear history | ✅ *Remove from library*, *Remove unavailable*, *Remove from history* (right-click on Home), *Settings → Privacy → Clear history…* (asks first), *Remember history* and *Resume* switches |

## 1. Test results

| Suite | Result |
|---|---|
| Database, scanner, history rules, playlists: `tests/unit/test_library_db.py` | 30 passed |
| Service (fake probe): `tests/unit/test_library_service.py` | 6 passed |
| UI (mock engine): `tests/ui/test_library_ui.py` | 22 passed |
| Real engine: `tests/integration/test_library_engine.py` | 49 passed (45-file corpus probe, invalid files, cancel, thumbnails, resume ×3) |
| Full default suite | **391 passed**, 72 skipped (opt-in mpv runs), 0 failed, in 2 consecutive runs; unit + UI 260 passed after the final styling fixes |
| ruff and strict mypy | clean |

## 2. Measurements

| What | Result | Tool |
|---|---|---|
| Thumbnail + metadata per video (libVLC) | 0.1–0.7 s (4K HEVC and MPEG-2 1080i are the slowest); audio files 0.02 s | spike, `test_probe_reads_corpus_file` |
| Whole corpus (45 files, including 5 broken ones) | 22 s scan + metadata | service trial run |
| 2,000 files, service alone (fake probe) | scan 1.9 s, metadata 3.6 s | profile run |
| 2,000 files with the UI running | 7.4–14 s in total; worst UI timer gap 106–124 ms | `test_scanning_keeps_the_ui_responsive` |
| Resume error, 1-hour file | −10 ms (12 runs) | `test_resume_is_accurate_across_app_restarts` |

## 3. Defects found and fixed

| ID | Defect | Fix |
|---|---|---|
| R25 | A damaged library database crashed start-up: the failed connection held the file open, so Windows refused to move it aside | Close first. If the file still cannot be moved, use an in-memory library and never overwrite the damaged file |
| R26 | Thumbnails came out grey and a quarter wide: python-vlc's callback type made the RV32 request read-only | Own callback type with a writable chroma pointer |
| R27 | python-vlc `tracks_get` dereferenced NULL for parsed media | Shared ctypes reader `read_media_tracks` |
| R28 | Thumbnails were silently not saved: `QImage.save` rejects a bytes format at runtime | Format from the file suffix |
| R29 | The "database was damaged" notice was overwritten at once | Shown after the engine's status line |

## 4. Limitations and open items

1. **Two TS files have no thumbnail** (`c_h264_ac3_720p.ts`, `e_corrupt_midstream.ts`): no
   picture was decoded within 4 s after seeking. They show a placeholder; duration and codecs
   are still read. MPEG-PS (`.mpg`) reports no codec names from preparsing.
2. **History follows the path.** Moving or renaming a file starts its history fresh. Duplicate
   detection uses the content key, but resume does not.
3. **Rotation:** thumbnails are upright, while the stored size is the coded size (640×360
   for a 90° file).
4. **Real-world scan speed** is dominated by thumbnail decoding (about 0.2–0.7 s per video,
   one file at a time). Large libraries fill in gradually; the grid stays usable meanwhile.
5. **Carried forward:** M5 subtitle render check (CONDITIONAL item); mpv multi-instance crash
   S1; large-resize stall R19.

## 5. Changes in this milestone

- New `library/` layer (database, scanner, service, history rules, models) and the
  `playback/media_probe.py` contract with `adapters/libvlc_probe.py`
  ([architecture overview](../../architecture/overview.md#library-history-and-playlists-m6)).
- UI: *Library* page (Ctrl+L) with grid, search, sort, folders dialog and playlists; Home
  dashboard; history, resume and play queue in `PlayerPage`; *Settings → Privacy* controls;
  **N/P/Home** keys; drop a folder to add it.
- Preferences: `remember_history`, `resume_playback`, `library_sort`.
- Evidence: `tools/library_screenshot.py` → [`evidence/`](evidence/): `library_empty.png`,
  `library_grid.png`, `library_search.png`, `library_playlists.png`,
  `home_continue_watching.png`, `settings_privacy.png`. Each was inspected before it was kept.
  The first captures showed unstyled list, search and tab widgets (light backgrounds, nearly
  invisible text); those styles were added to the theme and the pages recaptured.
  The capture tool refused two shots because another window covered the player (R16 check);
  they were taken again.
