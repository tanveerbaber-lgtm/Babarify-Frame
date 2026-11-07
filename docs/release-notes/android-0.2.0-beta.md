# Babarify Media Player for Android 0.2.0-beta

The first public Android beta. For Android 10 or later. Free, no account, no ads, and no internet permission:
the app can't send anything anywhere. Licensed under the GNU GPL v3 or later.

## Install

Download the APK for your phone (`arm64-v8a` for most phones from 2017 on, `armeabi-v7a` for older ones) and
open it. Android asks you to allow installing from that source. Check the file against `SHA256SUMS.txt`.

## What's in it

- **Video and audio** with libVLC: speed, chapters, A-B repeat, sync and delay, picture controls, zoom, rotate
  and flip, snapshots, subtitles with their look and preferred languages, and a small floating window.
- **Music:** every song on the phone by song, album, artist and folder, with search and sorting, once you allow
  it. Select several songs to play, queue, add to a playlist, hide or delete them.
- **Now playing:** the song's picture with colours taken from it, or an animation; a mini player on the main
  screens; a home screen widget; and the notification, which keeps audio playing with the app closed.
- **Queue, favourites and playlists**, with automatic lists, M3U import and export, and lyrics.
- **For you:** a recap of what you've played, worked out on the phone.
- **Equalizer** with presets, bass boost and preamp; fade between songs; a sound effect.
- **Your way:** seven colour themes including Light, your own background picture, edited song details and
  covers, set as ringtone, and a backup of your settings and lists.

## Permissions

- **Music (optional):** to list the songs on the phone. The app works without it.
- **Playing in the background:** so audio keeps playing after you leave the app.
- **Modify system settings (optional):** only for *Set as ringtone*. Android asks you to turn it on first.

Songs are deleted only when you choose *Delete from device* and confirm in Android's own prompt.

Not included yet: network streams and local AI subtitles.
