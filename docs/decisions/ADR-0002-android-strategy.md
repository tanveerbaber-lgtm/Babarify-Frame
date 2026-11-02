# ADR-0002: Android strategy

- **Status:** **Accepted** — accepted by Tanveer Baber on 2026-11-02 with M12.
- **Date:** 2026-11-02
- **Deciders:** Tanveer Baber (owner). Prepared by Claude (Claude Code) from M12 evidence.
- **Evidence:** [M12 report](../milestones/M12/acceptance-report.md),
  [capability matrix](../milestones/M12/capability-matrix.md),
  [licensing review](../milestones/M12/licensing-review.md),
  [`android_probe.json`](../milestones/M12/evidence/android_probe.json)

## Context

M13 needs a UI approach and a playback engine for an Android player. The Windows app is Python,
PySide6 and libVLC. Both engines below were built into a real prototype and run on one phone: a
Samsung Galaxy A33 5G (SM-A336E, Exynos 1280) on Android 16.

## Engine: evidence

| Criterion | Media3 1.11.1 | libVLC 3.7.7 |
|---|---|---|
| Video test files showing a picture (of 19) | 14 | **19** |
| Fails on this phone | 10-bit HEVC, WMV, Theora; MPEG-2 ×2 play sound with no picture | none |
| Audio-only files advancing (of 7) | 7 | 7, after one unexplained failure on 2 files (see report) |
| Hardware decoding of H.264 and 4K HEVC | yes | yes |
| AC-3 audio | through Samsung's `c2.dolby` decoder, so it depends on the phone | not dependent on it here (no `c2.dolby` decoder logged) |
| Truncated or non-media file | **precise error** | reports "ended" at 0 with no frames; the app must interpret it |
| Picked file (`content://`), seek, rotate, leave and return | works | works |
| APK size, arm64 | **2.7 MB** | 54.1 MB |
| Permissions added by the library | 2 (`ACCESS_NETWORK_STATE`, `WAKE_LOCK`) | **0** |
| Same engine family as the Windows app | no | **yes** |
| Licence as published | Apache-2.0 | LGPL-2.1 in the POM |

Not compared, because the measurements differ between engines: time to first frame and dropped
frames. Not measured: battery, memory, heat.

## Decision

**Build M13 as a native Kotlin app using libVLC, behind a small engine interface that keeps Media3
possible.**

- **Why libVLC:** the product promises to play the user's files. On this phone, Media3 could not
  show 5 of the 19 test videos, and what it can play depends on the phone's own decoders. libVLC
  played all 19 and matches the Windows engine, so format behaviour and known problems carry over.
- **What it costs:** an app about 20 times larger, and a damaged-file case the app must detect.
- **What would change this:** a device matrix in M13 showing libVLC failing where Media3 works, or
  the owner valuing a small download over format coverage. Then the choice can be Media3, or
  Media3 first with libVLC as a fallback. The prototype's `PlayerEngine` shows the swap is small.

## UI approach

Only native Kotlin was actually built. The others are assessed on paper, from what the project
needs, and were not prototyped.

| Option | Assessment | Evidence |
|---|---|---|
| **Native Kotlin** (proposed) | Direct access to the picker, lifecycle, surfaces and system bars. Both engines work from it. | **Prototype** |
| Flutter | Would need a bridge to the engine's video surface. Its gain is sharing UI with iOS, which M14 has not evaluated yet. | Paper |
| Qt / PySide on Android | Closest to the desktop code, but the desktop UI is built for mouse and windows, and the plan warns against forcing desktop assumptions onto mobile. | Paper |
| React Native | Same bridge cost as Flutter, and no existing JavaScript in the project to reuse. | Paper |

Whether the UI uses Compose or Android Views is left to M13. The prototype uses plain Views only to
keep its dependencies small, so it says nothing about Compose.

## Consequences

- Python code is not shared with Android; what carries over is listed in
  [shared contracts](../milestones/M12/shared-contracts.md).
- M13 must ship per-ABI builds or an App Bundle to control size, plus licence notices and a source
  offer ([licensing review](../milestones/M12/licensing-review.md)).
- All results come from one phone. M13 must define and test a device matrix before anything is
  called supported.
- iOS is decided separately in M14. Choosing Kotlin here does not decide it.
