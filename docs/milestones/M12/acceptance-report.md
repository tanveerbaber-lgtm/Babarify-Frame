# M12 Acceptance Report — Android Feasibility and Shared Architecture

**Date:** 2026-11-02 · **Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **PASS** — accepted by the owner on 2026-11-02, with the limits in §4

M12 is a feasibility milestone and asks for a strategy based on a real prototype. That exists, and
it ran on a real phone. Nothing here shows that an Android app is ready, and none is claimed.

**Direction** ([ADR-0002](../../decisions/ADR-0002-android-strategy.md), accepted): native Kotlin
with libVLC. Media3 stays possible behind the engine interface.

M11 stays CONDITIONAL: its beta has no reports yet, and M12 did not touch the Windows app.

## Acceptance criteria (plan §8, M12)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | Strategy is based on a real prototype and dependency review | **Met, on one phone** | `android/prototype/`, [`android_probe.json`](evidence/android_probe.json), [licensing review](licensing-review.md) |
| A2 | Shared contracts are portable, not desktop assumptions forced onto mobile | **Met as a written contract** | [shared-contracts.md](shared-contracts.md) names what must not carry over; only the engine interface was exercised in code |
| A3 | Permissions and media access follow platform rules | **Met** | The prototype requests no permissions; files came through the system picker (`content://`, [`picker_check.log`](evidence/picker_check.log)); Android refused a folder the app didn't own (§3) |
| A4 | No Android release is claimed until tested on supported devices | **Met** | No release; prototypes use a debug key and were removed from the phone |

### Deliverables

| Deliverable | Status |
|---|---|
| Mobile requirements and UX scope | ✅ [mobile-requirements.md](mobile-requirements.md) (proposal; 3 owner questions) |
| Evaluation of native or cross-platform UI options | ✅ [ADR-0002](../../decisions/ADR-0002-android-strategy.md): native built; the others on paper only |
| Android playback engine feasibility prototype | ✅ `android/prototype/`, `tools/android_probe.py` |
| Shared data models and portable contracts | ✅ [shared-contracts.md](shared-contracts.md) |
| Platform-specific capability matrix | ✅ [capability-matrix.md](capability-matrix.md) |
| Mobile licensing and packaging review | ✅ [licensing-review.md](licensing-review.md), with open items for M13 |

## 1. Test setup

- **Phone:** Samsung Galaxy A33 5G (SM-A336E, Exynos 1280), Android 16 (API 36), the owner's phone.
- **Prototype:** one Kotlin app built per engine: Media3 1.11.1, libVLC 3.7.7. Target API 37, minimum 26.
- **Automated:** `tools/android_probe.py` played 19 video, 7 audio-only and 4 damaged files, and 2
  subtitle pairs, for up to 9 s each, then seek, rotation, and leave-and-return tests.
- **Owner:** picked their own video through the system picker in each app and confirmed it played
  with sound.
- **Build tools:** the Android SDK already on the PC; Gradle 9.8.1, AGP 9.5.0.

## 2. Results

Full tables are in the [capability matrix](capability-matrix.md).

| | Media3 | libVLC |
|---|---|---|
| Video files with a picture (of 19) | 14 | 19 |
| Audio-only files advancing (of 7) | 7 | 7 (see §3) |
| Seek to 20 s | lands, continues | lands, continues |
| Rotation: position before → after | 4474 → 4561 ms | 4652 → 4652 ms |
| Leave and return: position kept | 6241 ms | 6151 ms |
| Audio while away | none | none |
| Own file through the picker | plays (owner confirmed sound) | plays (owner confirmed sound) |
| arm64 APK | 2.7 MB | 54.1 MB |

Crashes: none in the crash log during the final picker runs.

## 3. Findings

**In the prototype, found by this work:**

1. **Controls under the navigation bar (owner found).** Android 15+ draws apps behind the system bars,
   and the prototype ignored that, so the owner couldn't use the buttons. Fixed using window insets;
   confirmed by screenshot on the libVLC build and by the owner's use of both.
2. **A picked file was ignored.** Android delivers the picker's result after `onStart`, and the code
   only opened the file if an engine already existed. Fixed; the log shows both engines opening a
   `content://` file.

These are prototype defects with no automated test. **M13 must have regression tests for both.**

**About the engines:**

3. **libVLC reports truncated and non-media files as "ended", not as an error**, about 65 ms after
   opening, at position 0 with no frames. It's detectable, so M13 must turn it into a message.
4. **An unexplained libVLC result.** In the full run, Opus and Vorbis files did not advance (position
   0). Twelve direct reruns all advanced, with audio reported as playing. The cause is unknown, so
   this may be an intermittent defect. M13 must repeat it in its test matrix.
5. **Media3's formats depend on the phone.** AC-3 here went through Samsung's `c2.dolby` decoder, and
   10-bit HEVC failed on this phone's decoder. Expect different results on other phones.

**About the setup:**

6. **Android enforced folder ownership.** A folder the runner created through adb could not be read
   by the app (`ERROR_CODE_IO_NO_PERMISSION`). It was a runner mistake, now fixed, and it's also
   evidence that the access rules apply to the prototype.
7. **Unstable USB.** The connection dropped repeatedly, and the phone sometimes needed approving
   again. The runner records results after each file and resumes. A locked phone once produced false
   failures, so runs that end with the phone locked no longer count.

## 4. Limits of this evidence

- **One phone, one Android version.** No other device has been run, and nothing is called supported.
- **Sound was checked by ear once per app,** on the owner's own video. Other files show only that
  position advanced.
- **The owner's check confirmed play and sound.** The buttons were reachable and Open worked, but the
  log can't show whether Play/Pause and ±10 s were each used.
- **First-frame time and dropped frames are not compared** between engines, because they measure
  different things. libVLC's figure marks video output starting, not a rendered frame.
- **Subtitles:** libVLC's SRT was seen in a screenshot. Its ASS run passed only the pixel check. Media3
  loaded both, but the prototype has no subtitle display for it, so its rendering is unknown.
- **The "no picture" verdict for subtitle runs is not reliable:** the test video is black. It's
  recorded as measured in the JSON, and these rows are read from the screenshot and tracks instead.
- **Not measured:** battery, memory, heat, long playback, AI, network streams.
- **`tools/android_probe.py` has no automated tests.** It needs a phone, and its results were read by
  hand. The first picture check is a coarse pixel sample.

## 5. For M13

Owner decisions still open: the 3 questions in the [requirements](mobile-requirements.md), including
how to distribute. Engine and UI are decided (ADR-0002).

Required work carried over: regression tests for findings 1–2; damaged-file message (3); repeat
Ogg audio (4); device matrix; libVLC contents and source check, licence notices, and a decision on
patents ([licensing review](licensing-review.md)); the Media3 permissions, if Media3 is ever used.

## 6. Changes

- `android/prototype/`: the prototype, with the Gradle wrapper.
- `tools/android_probe.py`: phone test runner.
- `docs/decisions/ADR-0002-android-strategy.md`; `docs/milestones/M12/`.
- No change to the Windows app or the published 0.9.1 beta.
- On the phone: both prototypes and their test files removed; nothing else changed.
