# Beta test scenarios (M11)

Testers run these on their own PC with their own media. Record each as **pass**, **fail** (open
a Problem report with the scenario ID) or **skipped**. Use only files you are happy to describe
in public (a report never needs the file itself).

## INS — Installation, update, uninstall

| ID | Steps | Pass when |
|---|---|---|
| INS-1 | Check the installer: `Get-FileHash .\BabarifyMediaPlayer-<version>-setup.exe -Algorithm SHA256` | The hash matches `SHA256SUMS.txt` |
| INS-2 | Run the installer (Full). Note what SmartScreen shows. | Installs without administrator rights; Start menu entry; the app starts |
| INS-3 | Install with *Compact* | Installs; *Settings → AI features* says the component is not installed |
| INS-4 | Tick "Open with", then right-click a video → Open with | Babarify Media Player is offered; your default player is unchanged |
| INS-5 | Install a newer beta over the old one | Settings, library and history are still there |
| INS-6 | Uninstall from *Settings → Apps*; answer **No** to deleting data | Program gone; reinstalling shows your settings again |
| INS-7 | Uninstall again; answer **Yes** | `%APPDATA%\Babarify` and `%LOCALAPPDATA%\Babarify` are gone; your media untouched |

## PLY — Playback

| ID | Steps | Pass when |
|---|---|---|
| PLY-1 | Open 5 of your own videos of different kinds (phone video, 4K, old .avi, .mkv with several tracks) | Each plays with sound; seeking works |
| PLY-2 | Play, pause, seek with ←/→, volume ↑/↓, mute, speed 1.5× | All respond at once |
| PLY-3 | Fullscreen (F), move the mouse, wait | Controls hide and come back; Esc leaves |
| PLY-4 | Open a damaged or non-media file renamed to .mp4 | A clear message; the app keeps working |
| PLY-5 | Play an audio file | The audio view shows; playback works |
| PLY-6 | Point at the seek bar of a local video | A picture, time and chapter (if any) appear |
| PLY-7 | Open a network stream you are allowed to use (Ctrl+N) | It plays, or the message explains why not |

## SUB — Audio tracks and subtitles

| ID | Steps | Pass when |
|---|---|---|
| SUB-1 | File with several audio/subtitle tracks: switch with V and B | Tracks change; names make sense |
| SUB-2 | Load an .srt file (Ctrl+Shift+O, or drop it on the video) | Subtitles show in time |
| SUB-3 | Adjust the subtitle delay (G/H) and the look (Settings) | Changes are visible |
| SUB-4 | (Full install) Generate subtitles for a short clip with speech | They appear, marked machine-generated |

## LIB — Library and history

| ID | Steps | Pass when |
|---|---|---|
| LIB-1 | Add a folder with videos | Files and thumbnails appear; no file is changed |
| LIB-2 | Search, sort, make a playlist, play it (N/P) | Works as expected |
| LIB-3 | Stop a film in the middle, restart the app | *Continue watching* resumes at the right place |
| LIB-4 | *Settings → Privacy → Clear history* | History is empty; library and bookmarks remain |

## SET — Settings

| ID | Steps | Pass when |
|---|---|---|
| SET-1 | Change several settings, restart | They are kept |
| SET-2 | *Reset to defaults* | Defaults return |
| SET-3 | Turn hardware decoding off during playback | Playback continues at the same place |

## ACC — Accessibility

| ID | Steps | Pass when |
|---|---|---|
| ACC-1 | Use only the keyboard: open a file (Ctrl+O), play, open menus (Alt), open and close dialogs (Tab, Enter, Esc) | Everything reachable; focus always visible |
| ACC-2 | With Narrator (Ctrl+Win+Enter): move through Settings and the player controls | Every control is announced with a meaningful name |
| ACC-3 | Windows display scale 150 % and text size 125 % | Nothing is cut off or overlapping |
| ACC-4 | High-contrast theme (Windows contrast themes) | Text and controls stay readable (record what you see) |

## PRV — Privacy

| ID | Steps | Pass when |
|---|---|---|
| PRV-1 | Use the app normally for a while with a firewall prompt or network monitor | No connection unless you open a stream or download a speech model |
| PRV-2 | *Help → Report a problem* | No file names unless you tick the box; nothing is sent |
