# Changelog

Released versions are published on the
[releases page](https://github.com/tanveerbaber-lgtm/Babarify-Media-Player/releases). Details for Windows
releases are in [`docs/release-notes/`](docs/release-notes/).

## Windows 0.10.0 (ready to publish, 7 November 2026)

Release notes: [0.10.0](docs/release-notes/0.10.0.md).

- Changed: the app is now called Babarify Media Player, and installs in a folder of that name. Upgrading moves it
  there and keeps your settings and library. A taskbar pin to the old copy has to be pinned again. New snapshots go to `Pictures\Babarify Media Player`; existing ones stay where they are.
- New: audio has its own screen, with the song's picture, title and artist, and colours taken from the picture.
  Songs with no picture get an animation: mirrored bars with a reflection, capsules, waves, a circle or lights.
  They change by themselves while a song plays, or you can choose one. They don't follow the sound.
- New: repeat off, this file or all, remembered between sessions.
- New: shuffle, and a queue you can jump around in, for playlists.
- New: a sleep timer that pauses playback.
- New: the Library has Songs, Albums and Artists tabs, from your folders' tags and pictures, with search, sorting,
  Play and Shuffle. Existing songs are read once more, in the background, the first time this version runs.
- New: seven colour themes in Settings, including Light, and Bass boost and Preamp dials on the equalizer. The
  bass dial turns up the four lowest equalizer bands.
- Changed: Settings, Theme and Animation now sit together at the bottom of the left bar, in place of About, which
  stays in the Help menu. Theme and Animation switch quickly from there.
- Changed: all text is Arial, bold for titles and headings. The home page shows the name once, in brand colours.
- New: favourites, with a heart on the player, and automatic Favourites, Recently played, Most played and
  Recently added lists.
- Changed: in full screen, audio keeps its controls until you hide them.
- Changed: the player's control buttons are larger, with bolder icons that are easier to see.
- Changed: clearer tabs, buttons and side bar icons; buttons lift with a soft shadow when you point at them.
- Changed: the status bar along the bottom is hidden unless you switch it on in Settings or the View menu.
- New: Play next and Add to queue from a song's menu.
- New: hide files from the library, and bring them back in Settings. The files aren't touched.
- New: delete from disk, which asks first and moves the file to the Recycle Bin.
- New: lyrics from an .lrc or text file, or typed in, that follow along when they have times.
- New: a For you tab: a recap of what you've played, top songs, artists and albums, and songs never played.
- New: edit a song's title, artist, album and cover. Saved in the app; the file isn't changed.
- New: your own picture as the background of the main pages.
- New: fade between songs in a playlist or queue, and a sound effect: room, wider stereo or both (Settings → Playback).
- New: back up settings, playlists, favourites and hidden files to a file, and restore them.
- New: import and export playlists as M3U.
- New: sort songs by folder, oldest first, most played or year. Songs are read once more for their year.
- New: volume from 1 to 100, with optional boost to 200.

## Android 0.2.0-beta (ready to publish, 7 November 2026)

Brings the Android app close to the Windows app. Release notes: [Android 0.2.0-beta](docs/release-notes/android-0.2.0-beta.md).

- Changed: the app is now called Babarify Media Player.
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
- New: an opening animation in 3D with the icon and name when the app starts. Tap to skip it. Android 12 and later
  no longer show the icon twice at start-up.
- New: Play next and Add to queue, selecting several songs, and hiding songs (Settings brings them back).
- New: delete songs from the phone, always after a confirmation.
- New: lyrics from an .lrc or text file, or typed in, that follow along when they have times.
- New: a For you screen: a recap of what you've played, top songs, artists and albums, and songs never played.
- New: a home screen widget with play controls.
- New: edit a song's title, artist, album and cover. Saved in the app; the file isn't changed.
- New: set a song as the ringtone. This needs one new permission, which Android asks for.
- New: your own picture as the background of the main screens.
- New: fade between songs in a playlist or queue, and a sound effect: room, wider stereo or both (Settings → Playback).
- Changed: text uses Arimo, which matches Arial, and the name on Home has the brand colours.
- New: back up settings, playlists and favourites to a file, and restore them.
- New: import and export playlists as M3U. Songs are matched by file name.
- New: sort songs by folder, oldest first, most played or year.
- New: seven colour themes, a sleep timer and touch lock. In Light, the player stays dark so its controls can be
  read over video.
- New: a mini player on the main screens: a card coloured from the song's picture, with its progress, title and
  artist. Swipe it sideways to change song.
- New: the notification shows the song's title, artist and picture, with a favourite button.
- New: audio files keep playing with the app closed, in a mini player in the notifications, until you close
  it there. Video stops when you leave unless you choose otherwise. This needs three new permissions; still no
  internet permission.
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
