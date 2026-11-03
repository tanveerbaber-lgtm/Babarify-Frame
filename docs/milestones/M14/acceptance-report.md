# M14 Acceptance Report — iOS Feasibility and Shared Architecture

**Date:** 2026-11-03 · **Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **CONDITIONAL** — accepted by the owner on 2026-11-03; M15 not started

Playback is feasible in the Simulator. M14 asks for more than that: its last criterion needs an
approved implementation scope, and that depends on a licensing and distribution decision the
owner hasn't made, plus an iPhone the project doesn't have.

**Direction** ([ADR-0003](../../decisions/ADR-0003-ios-strategy.md), accepted): hold M15 until the
licence route, a real iPhone and an Apple Developer membership are settled. **Condition for PASS:** the
owner approves a scope (A4) once those are decided.

M11 stays CONDITIONAL, and M13's Android release stays held. M14 changed neither.

## Acceptance criteria (plan §8, M14)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | Feasibility demonstrated on Apple hardware or Simulator | **Met, Simulator only** | [`simulator_results.json`](evidence/simulator_results.json), from [GitHub run 41591020316](https://github.com/tanveerbaber-lgtm/Babarify-Frame/actions/runs/41591020316) |
| A2 | Restrictions and unsupported features documented | **Met, mostly from Apple's documents** | [platform review](platform-review.md), [licensing review](licensing-review.md) |
| A3 | No desktop-only assumption forced into the design | **Met on paper** | [platform review](platform-review.md#shared-contracts) |
| A4 | A realistic scope is approved before development | **Not met: owner's decision** | Proposed in the [platform review](platform-review.md#proposed-scope-for-m15); depends on the licence route |

### Deliverables

| Deliverable | Status |
|---|---|
| iOS technology and engine prototype | ✅ `ios/prototype/`, `.github/workflows/ios-probe.yml` (runs on branch `m14-ios-feasibility`) |
| App Store distribution and signing requirements | ✅ [platform review](platform-review.md#signing-and-distribution), not exercised |
| Media picker, sandbox and background review | ⚠️ Reviewed on paper; the picker was **not run** |
| Shared-contract and capability review | ✅ [platform review](platform-review.md) |
| Licensing and dependency review | ✅ [licensing review](licensing-review.md), route undecided |

## 1. How it was tested

The owner has no iPhone, and this PC can't run iOS tools. With the owner's approval, the prototype
ran on GitHub's hosted macOS 15 machines from a public branch, at no cost:

- **Environment:** Xcode 16.4, Simulator with an iPhone SE (3rd generation) profile, iOS 26.2.
- **Engines:** AVPlayer, MobileVLCKit 3.7.5 behind one `Engine` protocol.
- **Runs:** 13 video, 7 audio-only and 3 damaged clips, 1 external subtitle, then seek, rotation, and
  leave and return, per engine. Each clip plays for about 7 s.
- **Checks:** position advancing, a pixel sample of a screenshot, and viewing the subtitle and rotation
  screenshots by eye.
- **Repeat:** the app was built and run three times. Reported verdict counts match across the last two
  (the first didn't record them in the same way).

## 2. Results

| | AVPlayer | VLCKit |
|---|---|---|
| Videos with a picture (of 13) | 3 | 13 |
| Audio-only advancing (of 7) | 6 | 7 |
| Damaged files (of 3) | 3 clear errors | 1 error, 2 stop at 0 with no error |
| External subtitle | not attempted | seen on screen ([screenshot](evidence/vlckit_subtitle.png)) |
| Seek and rotation | work | work |
| Leave and return | **jumps to 16.666 s** | position kept |

Full table: [platform review](platform-review.md).

## 3. Findings

1. **VLCKit's format coverage matches Android's libVLC result;** AVPlayer's is limited to Apple's formats.
2. **The App Store is the deciding issue, not the technology.** VLC itself needed a rewrite and relicensing.
3. **VLCKit's LGPL label can't be taken at face value.** Its binary contains GPL notices and `x264` text.
   These are markers, not proof, but an LGPL-only route needs VideoLAN's build configuration checked.
4. **An unexplained AVPlayer result.** After returning from the background it landed on exactly 16.666 s
   in all 3 runs, whether it had been at 11, 13 or 19 s. It may be a Simulator effect or a prototype
   defect. It's unexplained, and it matters if AVPlayer is chosen.
5. **Damaged files on VLCKit behave as on Android:** a stop with no error, which the app must interpret.

**Mistakes during this work,** both fixed before being relied on: the first licence scan looked in the wrong
folder, so its zeros were meaningless, and track lists read after a clip ended came back empty.

## 4. Limits of this evidence

- **Simulator only.** It uses the host Mac's decoders. Nothing here shows real iPhone decoding, battery,
  memory, heat, or whether libVLC's font-scan stall (Android, 22 s) happens on a phone.
- **Sound was never heard.** Position advancing doesn't prove audio output, and the runner may have no
  audio device.
- **No picker.** Clips were bundled in the app, so real file access is untested.
- **No interruptions:** calls, Control Center, headphones and AirPlay.
- **Whether the app was truly silent or suspended in the background was not measured.**
- **Rules come from documents,** and some sources are old or secondary (noted where used).
- **App size unknown:** 46 MB is a Debug Simulator build, not an iPhone release.
- **UI:** the prototype has none. Native Swift is assumed; other UI options weren't built.
- **`run_probe.py`** has no automated tests of its own.

## 5. Owner decisions

1. **Licence route:** B, C or D in the [licensing review](licensing-review.md), with a lawyer's advice.
2. **Hardware and account:** a real iPhone (or a tester who has one) and the Apple Developer Program,
   99 USD a year, if M15 goes ahead.
3. **Scope:** approve or change the [proposed scope](platform-review.md#proposed-scope-for-m15).

The owner chose to merge the prototype and workflow into `main`.

## 6. Changes

- `ios/prototype/` (with about 8 MB of synthetic clips), `.github/workflows/ios-probe.yml`.
- `docs/decisions/ADR-0003-ios-strategy.md`; `docs/milestones/M14/`.
- No change to the Windows or Android apps. No Apple account used, nothing signed, nothing published.
