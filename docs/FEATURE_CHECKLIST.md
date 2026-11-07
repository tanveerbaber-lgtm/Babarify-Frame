# Feature checklist

Ideas from comparing with the Music Player app on the owner's phone (5 November 2026). Each box is ticked when the
feature is built and its tests pass. It still needs the owner's check before it is committed.

`[ ]` not started, `[~]` in progress, `[x]` built and tested

## Requested separately

- [x] Opening intro on Android: the icon and "Babarify Media Player", animated

## Batch 1: Library control

- [x] 1. Play next and Add to queue, from a song's menu (Android, Windows)
- [x] 2. Select several songs, then play them or add them to a playlist (Android)
- [x] 3. Hide songs, and a Settings page to bring them back (Android, Windows)
- [x] 4. More sort options: play count, year, folder, oldest or newest first (Android, Windows)
- [x] 5. Delete from device, with the system's confirmation (Android, Windows)

## Batch 2: Keeping your data safe

- [x] 6. Back up settings and playlists to a file, and restore them (Android, Windows)
- [x] 7. Import and export playlists as M3U (Android, Windows)

## Batch 3: Extras

- [x] 8. Your own lyrics: a local `.lrc` file or typed in, with auto-scroll (Android, Windows)
- [x] 9. Listening recap, worked out on the device (Android, Windows)
- [x] 10. "For you" page: most played, never played, favourite albums and artists (Android, Windows)
- [x] 11. Home screen widget (Android)
- [x] 12. Edit tags and change cover (Android, Windows)
- [x] 13. Set as ringtone, with one new permission (Android)
- [x] 14. Your own picture as the background (Android, Windows)

## Batch 4: Test first, then decide

- [x] 15. Try crossfade and gapless playback with libVLC, and report whether they work well
  - Gapless: not possible as things stand. Windows measured about 0.4 s between songs, whether the app loads the next
    file or uses libVLC's own list player.
  - Crossfade: looks possible. Two players ran at once on Windows, and starting the second early would also hide that
    gap. Changing their volumes wasn't confirmed, because the test ran with no sound output.
- [x] 16. Try reverb and virtualizer with libVLC, and report whether they work well
  - The Windows engine has the spatializer (VLC's room effect) and stereo widener, and Android's library mentions both.
  - Whether they sound good is unknown: they need listening to. The test couldn't tell either, since libVLC also kept
    playing when asked for a filter that doesn't exist.

## Left out on purpose

Ads, Premium and subscriptions; online lyrics; cloud transfer; free ringtones; voice recorder. The first four go
against the app being free and private, and the Android app has no internet permission. A voice recorder isn't a
media player feature.
