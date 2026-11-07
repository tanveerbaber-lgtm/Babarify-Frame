# Known issues — Babarify Media Player beta

Last updated: 2026-11-07 (0.10.0). Please do not report these again, but do add details to the
linked issue if you have new information.

| Area | Issue | Workaround | Since |
|---|---|---|---|
| Install | The installer is not code-signed: SmartScreen shows "Windows protected your PC" | Check the SHA-256 against `SHA256SUMS.txt`, then *More info → Run anyway* | 0.9.0 |
| Start-up | The first start after installing or updating takes about 15 s ("Starting playback engine…") while Windows scans the new files; later starts are quick | Wait for it once | 0.9.0 |
| Playback | DVD and Blu-ray discs are not supported (legal reasons) | — | 0.9.0 |
| Playback | Previous frame (,) is not available with the libVLC engine | Seek back a little | M7 |
| Playback | The time display does not move during frame stepping | It updates on play | M7 |
| Playback | Rotation restarts playback at the same position; 4K rotation stutters | — | M7 |
| Picture | Gamma is only available with hardware decoding switched off | Settings → Hardware decoding: Off | M7 |
| Sound | Volume above 100 % has no limiter and can distort loud passages | Use boost only for quiet files | M7 |
| Subtitles | One subtitle track is shown at a time | — | M5 |
| Streams | DASH streams are not supported; RTSP is fetched by libVLC directly | Use the HLS address if the service offers one | M8 |
| Previews | Some AV1 files show no preview picture for some positions; 4K previews are slow | — | M8 |
| AI | Generated subtitles are a machine draft; speed is about 6× real time (base model) on a mid-range laptop CPU | Use the tiny model for speed | M9 |
| Library | Moving or renaming a file loses its history, bookmarks and generated subtitles | — | M6 |
| Music | There is a short gap (about 0.4 s) between songs; playback can't run them together | Fade between songs makes the change smooth | 0.10.0 |
| Music | Fade between songs fades out and in; the songs don't overlap | — | 0.10.0 |
| Sound | The Room and Wider stereo effects are new and only lightly tested by ear | Tell us how they sound | 0.10.0 |
| Library | Edited details and covers are kept by the app, not written into the files, so other apps don't see them | — | 0.10.0 |
| Update | Going back to 0.9.1 after 0.10.0 starts 0.9.1 with an empty library (it can't read the newer one); your data stays for the next update | Keep using 0.10.0 | 0.10.0 |
| Accessibility | Windows contrast themes are not followed: the app keeps its own dark theme (all text at least 5.6:1 contrast, control outlines at least 3:1) | — | 0.9.0 |

Fixed in 0.9.1: control outlines were hard to see (low contrast). 0.10.0 renames the app to Babarify Media Player; see the release notes.
