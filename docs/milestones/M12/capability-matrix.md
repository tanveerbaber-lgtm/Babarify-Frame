# M12 — Platform capability matrix

**Measured** means run on the Samsung Galaxy A33 5G, Android 16, unless marked otherwise. One phone
says little about other phones, above all for Media3, which uses the phone's own decoders.

## Format results

"Plays" means position advanced and the screen showed a picture. Sound was checked by ear only on
the owner's own video in each app (H.264/AAC in the Media3 run). Decoders are from the logs; where
no system decoder was logged for libVLC, it is assumed to be decoding in software.

| File | Media3 | libVLC |
|---|---|---|
| H.264 1080p30, 1080p60, 720p120 (MP4) | plays, `c2.exynos.h264` | plays, `c2.exynos.h264`; 175 late frames at 120 fps |
| H.264 in MKV, portrait, rotated 90° | plays | plays |
| H.264 + AC-3 (TS) | plays, `c2.dolby.eac3` | plays |
| HEVC 8-bit 2160p (MKV) | plays, `c2.exynos.hevc` | plays, `c2.exynos.hevc` |
| HEVC 10-bit 1080p (MP4) | **fails**: decoding error | plays, software |
| VP9 1080p + Opus (WebM) | plays, `c2.android.vp9` | plays, `c2.android.vp9` |
| AV1 1080p + Opus (MKV) | plays, `c2.android.av1-dav1d` | plays, software |
| VP8 + Vorbis (WebM) | plays, `c2.exynos.vp8` | plays, `c2.exynos.vp8` |
| MPEG-2 576p, 1080i | **no picture**: track unsupported | plays, software |
| MPEG-4 + MP3 (AVI) | plays, `c2.sec.mpeg4` | plays, `c2.sec.mpeg4` |
| WMV2 + WMA2 | **fails**: container unsupported | plays, software |
| Theora + Vorbis (OGV) | **fails**: container unsupported | plays, software |
| Multi-track MKV | plays; 2 audio and 2 subtitle tracks listed | plays; 2 audio and 2 subtitle tracks listed |
| MKV without an index | plays | plays |
| Audio: AAC, MP3, FLAC, Opus, Vorbis, AC-3, PCM | all advance | all advance (Opus and Vorbis: see report) |
| Corrupt stream | plays through it, 8 frames dropped | plays through it, 2 frames dropped |
| Truncated MP4, not media | precise error | "ended" at 0, no frames, no error |
| Empty file | error | error |

## Capabilities

| Capability | Windows (shipped) | Android: libVLC | Android: Media3 |
|---|---|---|---|
| Local playback | Yes | **Measured** | **Measured** |
| Open through the system picker | n/a | **Measured** by the owner | **Measured** by the owner |
| Seek | Yes | **Measured** (by adb) | **Measured** (by adb) |
| Rotation keeps position | n/a | **Measured** | **Measured** |
| Leave and return keeps position | n/a | **Measured** | **Measured** |
| Silent while the app is away | n/a | **Measured** | **Measured** |
| Hardware decoding | Yes | **Measured** | **Measured** |
| Track listing | Yes | **Measured** | **Measured** |
| External SRT | Yes | **Seen on screen** | Track loaded; **display not built** |
| External ASS | Yes | Screen check only, not viewed | Track loaded; **display not built** |
| Sidecar subtitle matching | Yes | Not possible as on desktop (see requirements) | Same |
| Speed, equalizer, picture, snapshots, frame step | Yes | Not tested | Not tested |
| Network streams | Yes, with hardening proxy | Not tested; needs its own review | Not tested |
| Chapters and bookmarks | Yes | Not tested | Not tested |
| Local AI subtitles | Yes, separate worker | **Not evaluated** | **Not evaluated** |
| Battery, memory, heat | n/a | **Not measured** | **Not measured** |
| Android versions other than 16, other phones | n/a | **Not tested** | **Not tested** |

## Permissions

| Permission | Prototype manifest | Media3 adds | libVLC adds |
|---|---|---|---|
| Storage or media access | none | none | none |
| `ACCESS_NETWORK_STATE` | none | yes | none |
| `WAKE_LOCK` | none | yes | none |
| `INTERNET` | none | none | none |

Read from the built APKs with `aapt2 dump permissions`. The prototype has no internet permission, so
neither engine can reach the network.
