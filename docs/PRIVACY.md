# Babarify Media Player — Privacy notice

Babarify Media Player is a media player for your own files. It has **no account, no advertising, no
telemetry and no crash upload**. Nothing about you, your files or what you watch is sent to
the developer or anyone else.

## What stays on this PC

| What | Where | Why | How to remove |
|---|---|---|---|
| Settings | `%APPDATA%\Babarify\Frame\settings.json` | Your choices (volume, subtitles, picture…) | *Settings → Reset to defaults*, or delete the file |
| Library, songs' tags and pictures, history and play counts, bookmarks, playlists, favourites | `%APPDATA%\Babarify\Frame\library.db` and `thumbnails\` | Library page, *Continue watching*, resume, bookmarks, automatic playlists | *Settings → Privacy → Clear history*; remove folders and entries in the Library; history can be switched off |
| Generated subtitles and their search index | `%APPDATA%\Babarify\Frame\subtitles\` and the library database | Only if you use the optional AI features | *Settings → AI features → Delete all generated subtitles* |
| Speech models | `%LOCALAPPDATA%\Babarify\Frame\models\` | Only if you download one | *Settings → AI features → Delete model* |
| Logs and crash records | `%LOCALAPPDATA%\Babarify\Frame\logs\` | To help you (or someone you choose to share them with) understand a problem | Delete the folder at any time; old entries are trimmed automatically |
| Snapshots | `Pictures\Babarify Media Player` | Pictures you take with Shift+S | Delete them like any picture |

Logs can contain the names and folders of files you played and the addresses of streams you
opened. They are never uploaded; you decide whether to share them.

When you uninstall, you can choose to delete all of the above (except snapshots, which are your
pictures). Your media files are never changed or deleted by Babarify Media Player.

## When Babarify Media Player uses the network

Only when you ask it to:

1. **Network streams** you open (File → Open network stream, or a link you drop). The server
   you choose sees a normal request from "BabarifyMediaPlayer", like any player. Babarify fetches
   web streams itself and never follows a redirect or playlist entry to a local file or
   another program.
2. **Downloading a speech model** (Settings → AI features), after you confirm. The model comes
   from huggingface.co. Only the model files are requested, with telemetry switched off;
   nothing about you or your media is sent.

There is no automatic update check. To update, download a newer installer yourself.

## Optional AI features

They are off until you switch them on, and they run entirely on this PC. Video, sound and
subtitles are never uploaded. Generated subtitles are marked *machine-generated*.

## Contact

Questions about privacy: open an issue in the project's repository.

## Android

The Android app has no internet permission, so it cannot send anything anywhere. It reads the files you
open and the folders you add to the library, and it never changes them. If you tap *Find my music* and allow
it, the app also reads the list of songs on the phone, with their names, artists, albums and pictures, and
plays them. Android's permission for this is `READ_MEDIA_AUDIO` (`READ_EXTERNAL_STORAGE` on Android 12 and
earlier, where it can also see other files). The app works without it, and you can take it back in Android's
settings. The library, playlists, favourites, bookmarks, settings, recent files, how often you played each
song and your place in them stay on the phone, are excluded from backup and device transfer, and can be
cleared or removed in the app. *Settings → Privacy* switches off play history and clears it. A
subtitle file you add is copied into the app's private cache so the player can read it. Uninstalling
removes all of this, except snapshots you chose to take, which are saved in `Pictures/Babarify Media Player`
for you to keep.

Its other permissions are for sound that keeps playing after you leave: `FOREGROUND_SERVICE`,
`FOREGROUND_SERVICE_MEDIA_PLAYBACK` and `WAKE_LOCK`. Audio files always keep playing, even after closing
the app, until you close them from the notification. Video does so only if you choose that in *Settings →
When you leave a video*; otherwise leaving stops it. While sound plays on, the notification shows the file's
name, and the name also shows on the lock screen.
