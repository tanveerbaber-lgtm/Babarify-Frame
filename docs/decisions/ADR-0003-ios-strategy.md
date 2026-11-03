# ADR-0003: iOS strategy

- **Status:** **Accepted** — accepted by Tanveer Baber on 2026-11-03 with M14. M15 is held; the engine and licence route remain open.
- **Date:** 2026-11-03
- **Deciders:** Tanveer Baber (owner). Prepared by Claude (Claude Code) from M14 evidence.
- **Evidence:** [M14 report](../milestones/M14/acceptance-report.md),
  [platform review](../milestones/M14/platform-review.md),
  [licensing review](../milestones/M14/licensing-review.md),
  [`simulator_results.json`](../milestones/M14/evidence/simulator_results.json)

## Context

The owner has no iPhone. A prototype with AVPlayer and VLCKit 3.7.5 was built and run in the iOS
Simulator on GitHub's hosted Mac (iPhone SE 3rd generation profile, iOS 26.2, built with Xcode 16.4).
The Simulator decodes on the host Mac, so it can't show what real iPhone decoders or battery do.

## Engine: evidence

| Criterion | AVPlayer | VLCKit 3.7.5 |
|---|---|---|
| Test videos showing a picture (of 13) | 3 (H.264 MP4, HEVC, 10-bit HEVC) | **13** |
| Audio-only files advancing (of 7) | 6 (not Vorbis) | **7** |
| Multiple audio and subtitle tracks in MKV | can't open MKV | **listed** |
| External SRT subtitle | no API in the prototype's approach | **seen on screen** |
| Truncated or non-media file | **clear error** | stops at 0 with no error; the app must interpret it |
| Seek, rotation | works | works |
| Leave and return | landed on 16.666 s in all 3 runs, wherever it had been | **position kept** |
| Bundled size | **none** | about 99 MB framework before thinning |
| Licensing risk for the App Store | **lowest**: no third-party engine | **open**: see licensing review |

Not measured: real decoding, battery, memory, heat, sound by ear.

## Decision

**Don't start M15 yet.** Technically, native Swift with VLCKit is feasible and matches the Android
direction. Three things must be settled first, and none of them is technical:

1. **How it reaches people.** The App Store and the GPL have a known conflict. Decide this first,
   because it may rule out VLCKit or require relicensing.
2. **A real iPhone** for testing: the plan forbids declaring M15 complete without device validation.
3. **Apple Developer Program** membership (99 USD a year) for TestFlight or the App Store.

If the owner goes ahead, the recommended first version is native Swift with the same scope as Android
([scope](../milestones/M14/platform-review.md#proposed-scope-for-m15)). The engine depends on item 1:

- **VLCKit** if a licence route is confirmed: the full format range.
- **AVPlayer** if it isn't: legally simpler, but only MP4-family files, so it's a narrower product than
  the name promises. Its position anomaly must be understood first.

## Alternatives

| Option | Why not now |
|---|---|
| Start M15 now on the Simulator | The plan requires real-device validation, and the distribution question could undo the engine choice |
| Skip iOS | A legitimate outcome if the App Store route fails; Windows and Android don't depend on it |
| Flutter, Qt, React Native | Not prototyped. Each would still need one of these engines, so none solves the licensing question |

## Consequences

- Nothing is shared in code with Android beyond the written contracts (M12).
- A VLCKit-based App Store release may affect the licensing of Windows and Android too, if the owner
  chooses to relicense the project. That decision should cover all platforms.
