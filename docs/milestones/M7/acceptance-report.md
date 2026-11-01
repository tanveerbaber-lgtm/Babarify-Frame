# M7 Acceptance Report — Picture and Audio Enhancement

**Date:** 2026-10-31 · **Engine:** libVLC 3.0.24 x64 (mpv mapped, opt-in) ·
**Machine:** i7-8565U, Intel UHD 620, Windows 11, 3840×2160 @ 250 % ·
**Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **PASS** — accepted by the owner on 2026-11-01

All five acceptance criteria have recorded evidence. The access violation seen once during
M7 testing has been reproduced, explained and fixed (§1.1, R33). It was in the test setup,
not in the player: collecting the engine tests started a live mpv handle even though mpv
tests are off. After the fix, 20 soak runs of the full suite had no crash.

Every control offered maps to a libVLC function whose effect was measured: on screen (pixels)
for picture, geometry, rotation and frame stepping; in the output audio for the equalizer.
Controls the engine cannot do are disabled with a reason, never silently ignored. The work
found three defects (R30–R32), all fixed and guarded. The main limitations are documented
below and in the UI: rotation is expensive (4K stutters), gamma needs software decoding,
there is no backward frame step on libVLC 3, and the volume boost has no automatic limiter.

## Acceptance criteria (plan §8, M7)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Controls map to real engine functionality | **PASS** | `tests/integration/test_enhancements_engine.py` reads the screen of a real libVLC window: brightness, saturation, hue and contrast change the green test bar with **both** decoders, gamma with software decoding; 4:3 aspect and crop give a 15–35 % pillarbox; zoom 50 % leaves black borders; rotation turns the colour bars vertical; 5 frame steps change the picture and stay paused; the snapshot is a 1920×1080 PNG. Equalizer: `tools/equalizer_check.py` plays a 1 kHz tone: RMS 514 → 13 with the 1 kHz band at −20 dB, → 32 with the preamp at −12 dB, back to 514 when removed (all changed while playing); the 18 presets and 10 bands come from libVLC. |
| A2 | Unsupported controls are disabled or explained | **PASS** | Capabilities list each control per engine. The panel greys out what is missing and says why, e.g. "gamma … has no effect with hardware decoding; turn hardware decoding off in Settings to use it". The contract refuses unsupported values (`UNSUPPORTED`) instead of ignoring them (`test_unsupported_controls_are_refused_not_ignored`). Previous frame is disabled on libVLC; snapshot is refused for audio-only files. |
| A3 | Presets can be saved, applied and reset | **PASS** | Equalizer presets from the engine; named profiles (picture and equalizer) saved, applied, replaced by name and deleted, and kept in `settings.json` (at most 20; re-saving moves a profile to the end, R32); per-control Reset, *Reset picture*, *Reset equalizer*, *Reset all to defaults*. `test_profiles_save_apply_delete_and_persist`, `test_equalizer_presets_and_custom_bands`. |
| A4 | Picture/audio adjustments do not corrupt playback state | **PASS** | 120 rounds of picture, geometry and equalizer changes during real playback: still playing, position advancing, no errors (`test_many_adjustments_do_not_disturb_playback`); 60 rounds through the panel on the mock. A rotation restart keeps position, play state and picture settings (`test_restart_rotation_keeps_position_and_settings`). Values changed one after another apply correctly on both decoders (R30). |
| A5 | Performance impact and known limitations are documented | **PASS** | §2 table (`tools/enhancement_cost.py`, JSON in `tools/engine-benchmark/results/`), §3 limitations, and the in-app notes. |

### Deliverables

| Deliverable | Status |
|---|---|
| Aspect ratio and scaling | ✅ Aspect (16:9, 4:3, 16:10, 21:9, 2.35:1, 1:1, 5:4), zoom (fit, 50 %, 100 %, 200 %); per file |
| Rotation and crop where supported | ✅ Rotate 90/180/270, mirror, flip (libVLC: restarts at the same position); crop to the same ratios |
| Brightness, contrast, saturation and other picture controls | ✅ Plus hue and gamma (gamma with software decoding on libVLC) |
| Audio equalizer and presets | ✅ 10 bands + preamp, 18 libVLC presets, custom values |
| Volume boost with clipping safeguards | ✅ Off by default (*Settings → Allow volume above 100 %*); capped at 150 %; slider turns amber above 100 % with a distortion warning; a boosted volume is **never remembered** (next session ≤ 100 %); turning the option off brings the volume back to 100 %. See §3 for what this does not do. |
| A-B repeat, frame stepping, snapshot | ✅ **L** sets A, then B, then off (B must be after A); **.** next frame (**,** previous where the engine supports it); **Shift+S** saves a PNG to `Pictures\Babarify Frame` (never overwrites) |
| Reset controls and saved profiles | ✅ A3 |

## 1. Test results

| Suite | Result |
|---|---|
| Models and contract: `tests/unit/test_enhancements.py` | 22 passed |
| UI (mock engines with libVLC-like and reduced capabilities): `tests/ui/test_enhancements_ui.py` | 18 passed |
| Real libVLC, screen pixels: `tests/integration/test_enhancements_engine.py` | 8 passed |
| Full default suite, soak before the fix (20 runs, `tools/soak.ps1`) | 17 × **445 passed**; 3 crashed at collection (§1.1) |
| Full default suite, soak after the fix (20 runs) | **20/20 without a crash**; 19 × 445 passed; 1 test failure: the first picture sample was taken before software decoding showed its first frame. The test now waits for a picture, then 5/5 module runs passed |
| ruff and strict mypy | clean |

### 1.1 Test-run crash (found and fixed, R33)

One full-suite run during M7 ended with exit code 0xC0000005 (access violation) and no
Python stack. A soak of 20 full runs, each in a new process with `-X faulthandler`
(`tools/soak.ps1`), reproduced it 3 times. Every time it was within 6 seconds, during test
collection, in mpv's event thread (`mpv.py _event_generator`).

Cause: two engine test modules probe each engine to decide which tests to skip. The mpv
probe starts a live mpv handle to read its version and ends it at once, and it ran even
though mpv tests are off by default (M1 finding S1). The "handled" exception 0xe24c4a02
seen at collection since M5 came from the same probe; sometimes it turned into the crash.
The app itself never probes mpv, so users were not affected.

Fix: mpv is probed only when `BABARIFY_TEST_MPV=1`; otherwise its tests are skipped
without loading mpv. Collection now leaves `mpv` unimported. In 20 soak runs after the
fix there was no crash and no 0xe24c4a02 message.

## 2. Performance cost (libVLC, 1280×720 window, 6 s per row, one run each)

CPU is the player process, in % of one core; "dropped" counts frames dropped in the 6 s.

| File | Decoding | Baseline | Picture adjust | Equalizer | Aspect 4:3 | Rotate 90° |
|---|---|---|---|---|---|---|
| H.264 1080p30 | hardware | 2 % | 7 % | 5 % | 11 % | **37 %** |
| H.264 1080p30 | software | 29 % | 37 % | 21 % | 20 % | 41 % |
| HEVC 2160p30 | hardware | 10 % | 12 % (1 dropped) | 8 % | 5 % | **80 %, 126 dropped** |
| HEVC 2160p30 | software | 83 % | **174 %, 6 dropped** | 97 % | 94 % | **200 %, 126 dropped** |

Single runs vary by a few points (for example aspect 4:3 at 11 % against a 2 % baseline at
1080p). The clear findings: the equalizer, aspect, crop and zoom cost little. Picture
adjustment is cheap with hardware decoding but doubles CPU with software decoding at 4K.
Rotation copies every frame back to the processor: fine at 1080p, but at 4K about two thirds
of the frames are dropped on this PC. The Video tab says so.

## 3. Limitations

1. **Rotation (libVLC):** applied when the engine starts, so a change restarts playback at the
   same position. It costs a lot at 4K (§2). Rotation lasts for the session, not across app
   restarts.
2. **Gamma** has no effect with hardware decoding (D3D11 video processor), so it is offered only
   with software decoding. With hardware decoding, brightness looks about half as strong and
   contrast behaves differently than with software decoding (different libVLC filters).
3. **Frame stepping** is forward only on libVLC 3. While paused, libVLC reports no new time, so
   the time display does not move during frame steps (it updates on play).
4. **Volume boost has no limiter.** libVLC volume above 100 % is a plain gain: content that is
   already near full scale will clip. The safeguards are opt-in, a 150 % cap, a visible
   warning and never remembering a boost. A compressor filter was tried and its effect could
   not be verified, so it is not used or claimed.
5. **Equalizer accuracy:** the effect is measured (A1) but not calibrated in exact dB; libVLC
   presets are used as libVLC defines them.
6. **mpv (alternate engine):** picture, aspect, live rotation, frame step both ways and snapshot
   are mapped; crop, zoom and equalizer are reported unsupported; mpv mapping checked at API
   level only.
7. **A-B repeat** is checked on the 100 ms position poll, so the jump back to A can come up to
   about 0.1–0.25 s after B.
8. **Test note:** the M6 test `test_scanning_keeps_the_ui_responsive` (UI pause during a
   2,000-file scan, limit 250 ms) failed twice in about 20 full runs during M7 and passed in all
   others (worst pause 97–139 ms). It now reports its five longest pauses on failure, so the
   cause can be identified if it happens again.

## 4. Defects found and fixed

| ID | Defect | Fix |
|---|---|---|
| R30 | Adjustments changed one after another showed wrong colours (hardware decoding) or no change (software decoding) | Re-apply with the filter switched off and on |
| R31 | Dialogs drawn light with nearly invisible text (also the M5 Sync dialog and M6 folders dialog) | Dialogs use the dark page background |
| R32 | Re-saving a profile with a full list could drop it | A re-saved profile counts as the newest |
| R33 | Test run occasionally crashed at collection (access violation) | mpv probed only when mpv tests are switched on |

## 5. Changes

- `core/enhancements.py`; capability fields and the contract methods above
  ([architecture overview](../../architecture/overview.md#picture-and-sound-m7)).
- libVLC adapter: adjust filter (R30), aspect/crop/scale, equalizer and presets, transform
  filter in the shared-instance key, next frame, snapshot. mpv and mock adapters.
- UI: Picture & Sound panel (Ctrl+E), Video menu, A-B repeat, frame stepping, snapshots, volume
  boost option, profiles; preferences `picture`, `equalizer`, `profiles`, `allow_volume_boost`.
- Tools: `enhancement_cost.py`, `equalizer_check.py`, `enhancements_screenshot.py`, `soak.ps1`.
- Evidence ([`evidence/`](evidence/)): `picture_normal.png`, `picture_adjusted.png`,
  `aspect_4x3.png`, `panel_picture.png`, `panel_video.png`, `panel_audio.png`,
  `panel_profiles.png`. Each was inspected; the first panel captures showed the light dialog
  background (R31) and were retaken after the fix.
