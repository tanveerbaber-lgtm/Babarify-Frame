# Changelog

Released versions are published on the
[releases page](https://github.com/tanveerbaber-lgtm/Babarify-Frame/releases). Details for Windows
releases are in [`docs/release-notes/`](docs/release-notes/).

## Android 0.2.0-beta (not released)

Brings the Android app close to the Windows app. Not yet published.

- New: library of folders you choose, with search, sorting and pictures; playlists; bookmarks.
- New: speed, volume number from 1 to 100 and optional boost to 200, chapters, A-B repeat, sync and delay.
- New: picture controls, equalizer with presets, profiles, aspect, zoom, rotate, flip, snapshots.
- New: subtitle look, preferred languages, media and playback information, pictures while seeking.
- New: a redesigned interface: full-screen video with overlay controls, icons, bottom tabs and grouped settings.
- New: swipe gestures, sound in the background and a small floating window. Leaving the player still stops
  playback until you choose otherwise, and sound in the background needs three new permissions. Still no
  internet or storage permission.
- Not included: network streams and local AI subtitles, by the owner's decision.

## Android 0.1.0-beta (not released)

First Android version, for Android 10 or later. Built and tested, never published
([M13 report](docs/milestones/M13/acceptance-report.md)).

- Opens files through the system picker or "open with"; no permissions, no internet.
- Play, pause, seek, audio and subtitle tracks, external subtitle files.
- Recent files and resume, kept on the phone.
- Known: the first video after installing can take about 30 seconds to start.

## iOS (not started)

A feasibility prototype only, with no version planned yet
([M14 report](docs/milestones/M14/acceptance-report.md)).

## Windows (next version, not released)

- New: the volume number is shown next to the volume slider. Normal volume runs from 1 to 100; the mute
  button is how to silence it.
- Changed: volume boost now goes up to 200 % (was 150 %). It's still off until you allow it in Settings.

## Windows 0.9.1 (2026-11-02, public beta)

- New: *Help → Report a problem* prepares technical details for you to copy; nothing is sent.
- Fixed: outlines of controls were too faint (WCAG non-text contrast).

Full notes: [0.9.1](docs/release-notes/0.9.1.md).

## Windows 0.9.0 (2026-11-01, not published)

First packaged build: installer, playback, audio and subtitles, library, enhancement, network streams,
chapters and bookmarks, and optional local AI. Full notes: [0.9.0](docs/release-notes/0.9.0.md).
