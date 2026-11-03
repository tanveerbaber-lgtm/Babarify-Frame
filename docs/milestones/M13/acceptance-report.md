# M13 Acceptance Report — Android Implementation

**Date:** 2026-11-03 · **Build:** 0.1.0-beta · **Prepared by:** Claude (Claude Code) ·
**Decision owner:** Tanveer Baber

## Decision: **PASS** for the implementation — accepted by the owner on 2026-11-03; publishing held (§5)

The Android player is built and tested on the owner's chosen device matrix, and the owner confirmed
it on their phone. It is **not released**: no signing key exists yet, and §5 lists what must happen
before publishing.

Owner decisions: about 54 MB accepted (actual 56.4 MB arm64); GitHub releases; Android 10 or later,
with the owner's Galaxy A33 as the real device and an emulator for Android 10.

## Acceptance criteria (plan §8, M13)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | Tested on a defined device/OS matrix | **Met, with a thin matrix** | §1: one real phone, one emulator. Everything between is untested |
| A2 | Media access is permission-conscious | **Met** | No permissions requested (`aapt2`, and `theAppRequestsNoPermissionsAndHasNoInternet`); system picker or another app's "open with"; only `content:` addresses opened |
| A3 | Playback and lifecycle survive pause/resume | **Met** | `leavingReleasesTheEngineAndReturningContinues`, `aPausedFileStaysPausedAfterReturning`, `aFinishedFileComesBackAtItsStart`, `rotationKeepsTheSameEngineAndPosition`; owner check |
| A4 | No unexplained background media access or uploads | **Met** | The engine is released when the screen stops (test above); no internet permission, so nothing can be uploaded; backup and device transfer are excluded |
| A5 | Release packaging and third-party licences are reviewed | **Reviewed, with conditions** | §4; `tools/build_android_release.py` tried with a throwaway key |

### Scope delivered

Local playback; play, pause, seek, system volume; audio and subtitle track choice; external subtitle
files through the picker; system picker and "open with"; recent files, resume and preferences;
rotation without interruption; no background playback; stops for audio focus loss and unplugged
headphones; a clear message for damaged or unreadable files; licence screen.

Out of scope, as proposed in M12: network streams, library scanning, AI, equalizer, picture controls,
background audio, picture-in-picture, Android TV and tablet layouts.

## 1. Tests

| Device | Android | Device tests | Notes |
|---|---|---|---|
| Samsung Galaxy A33 5G (real phone) | 16 (API 36) | **18 of 18** | [`device_tests_galaxy_a33_android16.xml`](evidence/device_tests_galaxy_a33_android16.xml) |
| Emulator (Pixel 4 profile, x86_64) | 10 (API 29) | **18 of 18** | [`device_tests_android10_emulator.xml`](evidence/device_tests_android10_emulator.xml) |

- **Unit tests:** 9 of 9 (`PlaybackRulesTest`).
- **Lint:** no errors; the release tool fails on any.
- **Owner check on the A33, with their own videos:** the owner reported that everything on the
  checklist worked (picker, sound, controls, rotation, leaving and returning, Recent, tracks, subtitle
  file, volume, "open with", licences).

## 2. Defects found and fixed

The two M12 prototype defects now have tests. Everything is recorded as R47–R53 in the
[regression catalog](../../testing/regressions.md). New in M13:

| ID | Defect | Found by |
|---|---|---|
| R47 | First file after installing stalled ~22 s, then showed "could not be played" while it played anyway; leaving during the stall froze the screen ~16 s | Device test on the A33 |
| R48 | A finished file came back paused at its end | Device test |
| R49 | libVLC briefly reports 0 after reopening, which could overwrite the saved position | Device test |
| R50 | Android 12+ device transfer could have copied Recent to another phone (`allowBackup=false` doesn't cover it) | Lint warning |
| R51 | Two calls would have crashed on Android 10 (`readNBytes`, `WindowInsets.Type`) | Code review before the first run |

**Correction to M12.** R47 is the likely cause of libVLC failing M12's first setup check, which I put
down to the phone locking. The phone did lock during that session, so that isn't fully ruled out.
It doesn't explain M12's Opus and Vorbis result, because those weren't first opens. M13 ran those
two files 3 times each on both devices with no failure, plus 12 reruns in M12, so it hasn't
reappeared, but its cause remains **unexplained**.

## 3. Known limits

- **First video after install:** about 22 s on the A33 while libVLC scans the phone's fonts, with a
  "Preparing the player" message. It's a one-time wait per install, and may recur if system fonts change.
- **Not tested on real hardware:** Android 10–15, other brands, older and slower phones, and 32-bit
  (`armeabi-v7a` is built but never run).
- **Automated tests use the test provider, not Samsung's picker.** Only the owner's check covers the
  real picker, so a picker on another brand of phone is unverified.
- **Not tested by anyone, as far as recorded:** a phone call during playback and unplugging headphones.
  The code handles both, but the owner's checklist only suggested them.
- **Not measured:** battery, memory, heat, long playback sessions.
- **Sound** is checked only by the owner's ear; automated tests see the position advance.
- **Size** is 56.4 MB arm64 and 42.3 MB armeabi-v7a, with no shrinking attempted.
- **Subtitle styling** isn't offered on Android; the picked file isn't remembered across visits.
- **Accessibility:** controls have labels and 48 dp targets, but no TalkBack test has been done.
- **Unsigned:** nothing installable has been published.

## 4. Licensing and packaging

- **Dependencies:** all 33 runtime libraries were read from their POMs: 32 Apache-2.0 and libVLC
  LGPL-2.1 ([list](evidence/android_dependency_licences.txt)).
- **Contents of libVLC (closes the M12 item as far as a scan can):** a text scan of `libvlc.so` finds
  GPL version 2-or-later and version 3-or-later notices and LGPL notices, and no GPL-2.0-only text.
  It finds FFmpeg, x264, libass, FreeType and others. This is evidence and not a full audit: a scan
  can't prove what isn't there.
- **Notices:** the app ships its notices and the GPL-3.0, LGPL-2.1 and Apache-2.0 texts, under
  About and licences.
- **Our source:** the release tool produces a source archive from the commit.
- **libVLC's source:** VideoLAN publishes tag `libvlc-3.7.7` in `vlc-android`. Whether that alone
  meets the GPL's "corresponding source" duty, including its third-party libraries, is **not settled**.
- **Patents:** H.264, HEVC, AC-3 and others may raise licensing questions in some countries. The
  Windows beta has the same open question. **Not resolved.**

This is an engineering review and not legal advice.

## 5. Before publishing (owner decisions, nothing done yet)

1. **Signing key.** It's a long-term identity: lose it and people can't update without reinstalling.
   The owner decides where it lives and how it's backed up. It never goes in the repository.
2. **libVLC source.** Keep a copy of the matching source for as long as the build is distributed, as
   with Windows, or get advice that the VideoLAN tag is enough.
3. **Then:** build from a clean commit with `tools/build_android_release.py`, test the signed APK on
   the A33, and publish on GitHub as a pre-release, with known limits stated.

## 6. Changes

- `android/player/`: the app and its tests.
- `tools/build_android_release.py`; `docs/RELEASING.md`, `docs/PRIVACY.md`, `README.md`; R47–R53.
- No change to the Windows app or the 0.9.1 beta. M11 stays CONDITIONAL.
- **On the phone:** the app and test packages are removed. Install the signed build when one exists.
- **On this PC:** the Android 10 emulator image and emulator are in the SDK on C:, and the emulated
  device is in `E:\android-avd` (not in the repository).
