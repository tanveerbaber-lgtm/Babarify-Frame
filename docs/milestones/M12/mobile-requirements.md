# M12 — Mobile requirements and UX scope

A proposal for M13, for the owner to accept or change. It follows the plan's potential scope for M13.

## In scope for the first Android version

| Area | Requirement | Prototype status |
|---|---|---|
| Open files | Android's system picker, no storage permission | Works on one phone, both engines |
| Playback | Play, pause, seek, volume, position display | Play, pause and seek-by-adb work; volume uses system keys, not tested |
| Tracks | Choose audio and subtitle tracks | Listed by both engines; choosing not built |
| Subtitles | External SRT and ASS, opened through the picker | libVLC SRT seen on screen; picker route not built |
| History | Resume where you stopped, recent files, preferences | Not built |
| Screen | Rotation keeps position; controls stay clear of system bars | Works on one phone, both engines |
| Leaving the app | Playback stops and position is kept; no audio in the background | Works on one phone, both engines |
| Damaged files | A clear message, never a blank screen | Not built; engine signals are known |

## Out of scope for the first version

Each can return as a later decision: background audio, picture-in-picture, library scanning,
network streams, local AI, equalizer and picture controls, casting, Android TV, tablets as a
designed-for layout.

Network streams need particular care. The desktop app routes them through a hardening proxy
(R34), and that design has not been reviewed for Android.

## UX principles

- **Touch first:** large targets, gestures for seek and volume, no hover. The desktop UI is not ported.
- **Controls never sit under system bars.** The prototype got this wrong (see the report).
- **Honest about formats:** when a file can't be played, say so and say why where known.
- **Privacy matches desktop:** no account, no telemetry, nothing uploaded, no storage permission.

## Platform rules that shape this

- **Scoped storage:** apps read what the user picks. A persistent grant covers that one file, and
  the grant can be lost if the file moves, so history must handle a file that can't be reopened.
- **Sidecar subtitles:** a picked video does not grant access to the subtitle file beside it, so
  the desktop's automatic matching can't work the same way. The user picks the subtitle too, or
  grants a folder. This needs an M13 decision.
- **Edge-to-edge:** enforced for apps targeting Android 15 or later.
- **Lifecycle:** the app can be stopped or killed at any time, so position must be saved early.

## Open questions for the owner

1. Is a download of about 54 MB (arm64) acceptable? This is the main cost of libVLC.
2. Distribution: Google Play, GitHub releases, F-Droid, or a mix? Not reviewed yet.
3. Which phones and Android versions must M13 support? The prototype's minimum is Android 8 (API 26)
   only because it built there; only Android 16 has been run.
