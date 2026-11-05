# Known issues — Babarify Media Player beta

Last updated: 2026-11-01 (0.9.1). Please do not report these again, but do add details to the
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
| Accessibility | Windows contrast themes are not followed: the app keeps its own dark theme (all text at least 5.6:1 contrast, control outlines at least 3:1) | — | 0.9.0 |

Fixed in 0.9.1: control outlines were hard to see (low contrast); see the release notes.
