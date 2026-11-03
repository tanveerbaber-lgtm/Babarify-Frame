# M14 — iOS platform review

Measured results come from the Simulator run. Everything else comes from Apple's documentation and is
**not tested**. Rules change, so check them again before any release.

## Measured in the Simulator

| File | AVPlayer | VLCKit |
|---|---|---|
| H.264 + AAC (MP4) | plays | plays |
| HEVC 8-bit, 10-bit (MP4) | plays | plays |
| H.264 in MKV; multi-track MKV | can't open | plays; 2 audio and 1 subtitle tracks listed |
| H.264 + AC-3 (TS) | can't open | plays |
| VP9, VP8 (WebM); AV1 (MKV) | can't open | plays |
| MPEG-2; WMV; Theora | can't open | plays |
| MPEG-4 + MP3 (AVI) | time advances, **no picture** | plays |
| Audio: AAC, MP3, FLAC, Opus, AC-3, PCM | advances | advances |
| Audio: Vorbis (OGG) | fails ("Operation Stopped") | advances |
| Truncated, non-media | error | stops at 0 with **no error** |
| Empty file | error | error |
| External SRT | not attempted: AVPlayer has no simple way to add one | seen on screen |
| Seek to 20 s | lands, continues | lands, continues |
| Rotation (requested by the app) | continues | continues; video fills landscape |
| Leave and return | **jumps to 16.666 s, 3 of 3 runs, cause unknown** | position kept, 3 of 3 runs |

**Not comparable to Android's numbers:** the Simulator uses the host Mac's decoders. AVPlayer's format
list reflects Apple's supported containers, but a real iPhone hasn't confirmed it. libVLC's Android
font-scan stall didn't appear here, and the Simulator can't show whether it happens on an iPhone.

## Media access and sandbox

Per Apple's rules, apps "may not read or write data outside the designated container area"
([guideline 2.5.2](https://developer.apple.com/app-store/review/guidelines/)). So files would come
through the system document picker, as on Android.

- **Not demonstrated here.** The prototype plays clips bundled inside the app. The picker, and
  keeping access to a picked file between launches, need real testing in M15.
- **No library scanning**, as on Android.
- **Sidecar subtitles** can't be found automatically next to a picked file, as on Android; the user
  picks the subtitle too.

## Background and interruptions

- Background use must match its purpose, such as audio playback
  ([guideline 2.5.4](https://developer.apple.com/app-store/review/guidelines/)).
- **Proposed for M15:** stop when the app leaves the screen, as on Android. Background audio can be a
  later decision.
- **Not tested:** phone calls, Control Center, headphones and AirPlay. M15 requires interruption testing.

## Signing and distribution

| Route | Needs | Status |
|---|---|---|
| Simulator | A Mac; no Apple account was needed for this run | **Done here** |
| Own iPhone, free account | Apple says a free account lets you [test on your own devices](https://developer.apple.com/programs/whats-included/); an older forum post says such profiles last [about a week](https://developer.apple.com/forums/thread/53048), so check that | Not tried; no iPhone |
| TestFlight, App Store | [Apple Developer Program, 99 USD a year](https://developer.apple.com/programs/enroll/) | Not started |
| EU alternative marketplace or web | [EU users only](https://support.apple.com/en-mide/118110), under Apple's [alternative terms](https://developer.apple.com/support/alternative-app-marketplace-in-the-eu) | Not reviewed in depth |

Other rules that would apply:
- **Beta versions** belong on TestFlight, not the App Store ([2.2](https://developer.apple.com/app-store/review/guidelines/)).
- **Privacy policy** link required, in the app and its listing ([5.1.1](https://developer.apple.com/app-store/review/guidelines/)). The project has one to adapt.
- **Public APIs only** ([2.5.1](https://developer.apple.com/app-store/review/guidelines/)).
- **Code signing** needs a Mac with Xcode or a CI setup with Apple credentials as secrets. Nothing like this is set up.
- **Privacy declarations** aren't reviewed here, including how VLCKit fits them. M15 must cover them.

## Shared contracts

The M12 [shared contracts](../M12/shared-contracts.md) hold up: states, error codes, milliseconds and the
capability rule all apply. The prototype's `Engine` protocol served both engines, and VLCKit's silent stop
on damaged files maps to `media_open_failed` as it does on Android. That mapping is reasoned, not built.

Desktop-only items that must not carry over, in addition to M12's list: file paths as identity (iOS picker
access is bookmark-based, not tested), and anything that assumes free background processing, such as the
AI worker. Local AI wasn't evaluated.

## Proposed scope for M15

For the owner to approve, only after the three gates in ADR-0003.

**In:** system picker; play, pause, seek, system volume; audio and subtitle tracks; external subtitle files;
recent files and resume, on the device only; rotation; stop on leaving; handling of calls and headphones;
clear damaged-file messages; licence screen; VoiceOver labels.

**Out at first:** background audio, picture-in-picture, AirPlay, network streams, library, AI, equalizer,
iPad layouts, Apple TV.

**Must be tested on:** at least one real iPhone (none available now), the lowest supported iOS version, and
interruptions.
