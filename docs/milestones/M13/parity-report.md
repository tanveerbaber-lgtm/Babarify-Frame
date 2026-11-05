# Android feature parity report (0.2.0-beta)

**Date:** 2026-11-03 · **Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

The owner asked for the Android app to have features similar to Windows. This follows the
[M13 report](acceptance-report.md). **Nothing is published:** the M13 report's §5 still applies, so
publishing needs the signing key, the libVLC source decision and the patent question.

## Owner decisions

| Item | Decision |
|---|---|
| Background audio and picture-in-picture | Add |
| Network streams | Leave out. They would need the internet permission and a new design for the R34 hardening proxy |
| Local AI subtitles | Leave out. About 240 MB plus a model, internet to fetch the model, unknown speed on phones |

## Feature comparison with Windows

| Windows feature | Android 0.2.0-beta |
|---|---|
| Open files, "open with", resume, recent | ✅ (already in 0.1.0), and recent shows where you'll continue |
| Library: folders, search, sort, pictures, lengths | ✅ Through Android's folder picker, with no storage permission |
| Playlists, next and previous | ✅ |
| Bookmarks | ✅ |
| Chapters | ✅ |
| Speed; volume number; 1–100; boost to 200 | ✅ |
| A-B repeat, start over | ✅ |
| Sync and delay | ✅ |
| Audio and subtitle tracks, external subtitles | ✅ (already in 0.1.0); a chosen track now survives leaving and returning |
| Subtitle look | ⚠️ Size, colour, background. No font or position choice |
| Preferred languages, automatic subtitles | ✅ Matched against track names |
| Picture: brightness, contrast, saturation, hue | ✅ Applied live on the view |
| Gamma | ❌ A colour matrix can't express it |
| Equalizer, presets, profiles | ✅ |
| Aspect, zoom, rotate, flip | ✅ Crop is offered as *Zoom → Fill the screen* |
| Snapshots | ⚠️ Saved to `Pictures/Babarify Frame`, without colour changes or subtitles drawn separately |
| Frame stepping | ❌ libVLC for Android doesn't expose it |
| Pictures on the seek bar | ✅ While dragging, using the system's decoders, so not for every format |
| Media and playback information | ✅ Tags and format come from the system's decoders |
| Settings, reset, history off and clear | ✅ |
| Report a problem | ✅ Copies details, sends nothing |
| Network streams, local AI | ❌ Owner's decision above |
| Duplicate detection in the library | ❌ Not built |

Android only: swipe gestures for seek, volume and brightness; double-tap to skip; background audio with
a notification; small floating window; buttons to fill the screen and turn it.

## Owner's additions after acceptance

- **Repeat:** a player button cycling off, this file, all. It's remembered between sessions.
- **Playlists:** *Add media*, from the library or the system's picker, several at once.
- **Music mini player:** audio files keep playing after Back or closing the app, with a notification player,
  until closed from that notification. **This replaces "leaving stops playback by default" for audio.** Video
  still stops on leaving unless the user chooses otherwise.

- **Audio screen:** the screen went black seconds after a song started, because the auto-hide meant for video
  also ran for audio (R58). Audio now has its own screen, and its controls stay until hidden.
- **Music interface**, using a popular music player's store page and screenshots as a reference for layout only.
  No artwork or branding was copied, and the app itself was not run.
  - A Music tab with songs, albums, artists and folders, from Android's media index.
  - A now-playing screen with the song's picture, colours from it, shuffle, queue and favourites.
  - Five animations for songs with no picture, in the style of an image the owner supplied, changing every
    20 seconds or chosen by the user. **They are decoration and don't follow the sound:** that would need the
    microphone permission, which the app doesn't ask for.
  - Automatic favourites, recently played, most played and recently added lists.
  - An equalizer screen. Its bass dial turns up the four lowest equalizer bands.
  - Six colour themes, sleep timer, touch lock, a redesigned mini player and notification.

**The owner chose to add a music permission** so songs can be found without picking folders: `READ_MEDIA_AUDIO`, or
`READ_EXTERNAL_STORAGE` on Android 12 and earlier. It's asked for only when the user taps *Find my music*, and the app
works without it. On Android 12 and earlier it can technically see other files, which the app doesn't read.

## Interface

The owner asked for it to look like a real media player, so the interface was redesigned using the desktop
theme's colours and blue-to-cyan accent.

- **Player:** video across the whole screen, including behind the camera cut-out. Controls overlay it on dark
  gradients, and they and the system bars hide after about 4 seconds. Round play button, skip buttons showing
  the seek step, icon buttons, and the volume number beside its icon.
- **Main screens:** bottom tabs for Home, Library, Playlists and Settings; pictures and progress bars in lists;
  grouped settings with switches.
- **Icons** are the project's own vector drawings, so no icon library or new licence is involved. No new dependencies.

## Design changes

- **Playback moved out of the screen** into `PlaybackSession`, so sound can outlive it.
  `BackgroundPlaybackService` runs only when the user chose to keep sound playing.
- **Leaving a video stops it by default.** Background sound for video and the floating window are settings.
  Audio files play on, so M13's "nothing runs in the background" no longer holds for audio, by the owner's decision.
- **Three new permissions**, used only for sound that plays on: `FOREGROUND_SERVICE`,
  `FOREGROUND_SERVICE_MEDIA_PLAYBACK`, `WAKE_LOCK`. Still no internet or storage permission, and a
  test fails if the list changes. `POST_NOTIFICATIONS` isn't requested, as media session notifications are exempt.
- **`TextureView` replaces `SurfaceView`.** It allows a colour filter, rotation and snapshots with
  hardware decoding. The cost is some extra battery and GPU use, which hasn't been measured.
- **A new database, `library.db`.** `history.db` is unchanged, so 0.1.0 data would carry over. No 0.1.0
  was ever published, and upgrading from it wasn't tested.

## Tests

| Where | Result | Notes |
|---|---|---|
| Samsung Galaxy A33 5G, Android 16 | **78 of 78** | [`music_device_tests_galaxy_a33_android16.xml`](evidence/music_device_tests_galaxy_a33_android16.xml) |
| Emulator, Android 10 | **78 of 78** | [`music_device_tests_android10_emulator.xml`](evidence/music_device_tests_android10_emulator.xml). One test then gained a 1.5 s wait, and only the phone re-ran the whole suite after that |
| Unit tests | **39 of 39** | |
| Lint | 0 errors, 38 warnings | Not reviewed individually since the music interface; it was 22 before it |
| Owner's check of the music interface on the A33 | **"All works"** | An 18-step checklist with their own songs, covering the Music tab, now playing, animations, equalizer, mini player, notification, themes and video |
| Owner's check on the A33 | **"All works"**, before the redesign | A 10-step checklist with their own videos, covering library, playlists, boost, equalizer, background sound with the screen locked, small window, gestures, picture tools and subtitle look |

The owner also checked the additions on the A33 with their own songs and reported **"All works"**: a 12-step
checklist covering playlists, repeat, and the mini player after swiping the app away, with the screen locked and when closing.

All of these ran on the final code. One earlier A33 run stopped after 53 tests when USB dropped: the crash log
shows the test tool losing its connection, and no app error.

Device tests use real libVLC playback. Colour filter and subtitle colour tests read the actual screen.

## Defects found and fixed

Recorded as R54–R63 in the [regression catalog](../../testing/regressions.md).

| ID | Defect | Found by |
|---|---|---|
| R54 | Chapter names began with a space | Device test |
| R55 | On Android 10–12, other apps could have pressed play or pause in the small window | Lint |
| R56 | The controls could stay visible in the small window | Device test, once in Android 10's emulator |
| R57 | Closing the mini player could leave a dead notification behind | Device test |
| R58 | The screen went black seconds after a song started | The owner |
| R59 | Playing a song crashed the app on Android 10 | Device test |
| R60 | A very low bitrate MP3 opened part way ended at once and was called finished | Screenshot review |
| R61 | An audio test failed on and off, with the song playing normally | Device test |
| R62 | The notification kept the last song's title after a new list started another song | Screenshot review |
| R63 | Tapping a song in the list did nothing | Screenshot review |

Three intermittent results on the emulator, worth keeping an eye on:

- **Brightness test:** once read a black screen, then passed alone and in later runs. It now waits for the
  picture. The cause of that one reading wasn't established.
- **Subtitle colour test:** timed out once. The likely cause is the test, which could pick an embedded track
  before the added one had loaded. It now waits for the added one. Not proven by reproducing it.
- **R56:** the fix is also not proven by reproducing the failure, only by later runs passing. It has been
  seen on only one device and only once.

Neither failure has returned in the two full emulator runs and one phone run since, which is only a few runs.

R61's cause is taken from its logs, and the test passed 12 of 12 repeats and the last full runs after the fix. An
earlier fix also passed 12 of 12 and then failed in a full run, so it's worth watching. The mini player swipe test
failed on the A33 when it swiped straight after the player closed, and passed with a wait: the cause of that wasn't
established, beyond the screen still changing at the time. R60 was reproduced only with a silent 32 kbps file;
normal-sounding MP3s at 192 kbps and VBR resumed correctly.

## Known limits

- **Thin device matrix:** still one real phone and one emulator. Android 11–15, other brands and 32-bit are untested.
- **Boost:** the owner reports clear sound on their phone and videos. There's no limiter, so loud passages can distort.
- **Lock screen:** while sound plays on, the file's name shows in the notification and on the lock screen.
- **R57's second case** (music then video in a playlist) was fixed by always removing the notification. Where
  that one came from wasn't established.
- **Phone makers' battery rules** may stop background sound after swiping the app away on other phones. It worked on the owner's A33; automated tests can't do that swipe.
- **Not measured:** battery use with `TextureView`, background sound or the animations, memory, long sessions,
  very large libraries. The largest music list tested is a handful of songs.
- **Permission refused:** the Music screen's prompt after refusing isn't covered by a device test, because taking a
  permission back stops the app.
- **Reference app:** only its store page and screenshots were seen.
- **Library pictures and lengths** use the system's decoders, so a format only libVLC can play gets neither.
- **Language matching** relies on the words in a track's name, so an unnamed track can't match.
- **Not tested by anyone, as far as recorded:** phone calls, unplugging headphones, and folders on SD cards or cloud providers.
- **Accessibility:** a test checks the main player buttons have names, and controls have 48 dp targets, but no TalkBack test has been done.
- **Android 10's first full-screen video** shows the system's own "Viewing full screen" notice once, seen on the emulator.
- **Evidence doesn't cover the signed build.** The tests ran on debug builds; `RELEASING.md` already requires testing the signed APK before publishing.

## Changes

- `android/player/`: the features and interface above and `FeatureFlowsTest`, `EnhancementsTest`; version 0.2.0-beta.
- `docs/PRIVACY.md`, `CHANGELOG.md`, the plan's status, R54–R63.
- No change to the Windows app. M13's PASS stands for its original scope; this report doesn't change a milestone's decision.
- **On the phone:** 0.2.0-beta (debug build) is installed for the owner's use. It can't be updated by a build
  signed with the future release key without uninstalling first, and uninstalling removes its library and settings.
