# Changelog

Released versions are published on the
[releases page](https://github.com/tanveerbaber-lgtm/Babarify-Frame/releases). Details for Windows
releases are in [`docs/release-notes/`](docs/release-notes/).

## Windows, next version (not released)

- New: audio has its own screen, with the song's picture, title and artist, and colours taken from the picture.
  Songs with no picture get an animation: mirrored bars with a reflection, capsules, waves, a circle or lights.
  They change by themselves while a song plays, or you can choose one. They don't follow the sound.
- New: repeat off, this file or all, remembered between sessions.
- New: shuffle, and a queue you can jump around in, for playlists.
- New: a sleep timer that pauses playback.
- New: the Library has Songs, Albums and Artists tabs, from your folders' tags and pictures, with search, sorting,
  Play and Shuffle. Existing songs are read once more, in the background, the first time this version runs.
- New: favourites, with a heart on the player, and automatic Favourites, Recently played, Most played and
  Recently added lists.
- Changed: in full screen, audio keeps its controls until you hide them.
- New: volume from 1 to 100, with optional boost to 200 (already on main, listed here until released).

## Android 0.2.0-beta (not released)

Brings the Android app close to the Windows app. Not yet published.

- New: library of folders you choose, with search, sorting and pictures; playlists; bookmarks.
- New: speed, volume number from 1 to 100 and optional boost to 200, chapters, A-B repeat, sync and delay.
- New: picture controls, equalizer with presets, profiles, aspect, zoom, rotate, flip, snapshots.
- New: subtitle look, preferred languages, media and playback information, pictures while seeking.
- New: a redesigned interface: full-screen video with overlay controls, icons, bottom tabs and grouped settings.
- New: repeat off, one or all; shuffle; add media to a playlist from the library, your files or the player.
- New: a Music tab listing every song on the phone by song, album, artist and folder, with search and sorting.
  It asks for a new, optional permission to read songs; you can still open files and add folders without it.
- New: a now-playing screen with the song's picture filling the top, colours taken from it, or an animation
  if it has none: mirrored bars with a reflection, capsules, waves, a circle or lights. They change by
  themselves while a song plays, or you can choose one. Its controls stay until you hide them. The animations
  don't follow the sound.
- New: favourites, and automatic Recently played, Most played and Recently added lists.
- New: a queue you can jump around in, and shuffle that can be switched off again.
- New: an equalizer screen with preset chips, upright sliders, and bass boost and preamp dials.
- New: six colour themes, a sleep timer and touch lock.
- New: a mini player on the main screens: a card coloured from the song's picture, with its progress, title and
  artist. Swipe it sideways to change song.
- New: the notification shows the song's title, artist and picture, with a favourite button.
- New: audio files keep playing with the app closed, in a mini player in the notifications, until you close
  it there. Video stops when you leave unless you choose otherwise. This needs three new permissions; still no
  internet or storage permission.
- New: swipe gestures and a small floating window.
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
