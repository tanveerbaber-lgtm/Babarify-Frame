# M12 — Shared contracts

The Windows app is Python and the Android app would be Kotlin, so **no code is shared**. What can be
shared is meaning: names, values and rules. Generated code or a shared library would add a build
step for a small amount of simple data, so this is a written contract, kept beside the Python source.

## Portable: Android should use the same meaning

| Contract | Source | Notes |
|---|---|---|
| Playback states | `core/models.py` `PlaybackState` | `loading`, `playing`, `paused`, `buffering`, `ended`, `error`, and so on |
| Error codes | `core/errors.py` `ErrorCode` | Same codes. The user messages are portable in meaning; the wording can change for mobile |
| Track description | `core/models.py` `TrackInfo` | Kind, title, language, codec, selected; 0 means "not reported" |
| Capabilities | `core/models.py` `EngineCapabilities` | The rule carries over: **the UI disables or explains anything the engine reports as unavailable** |
| Subtitle style | `core/models.py` `SubtitleStyle.to_dict` | Same keys and limits; untrusted input falls back to defaults |
| Time | Milliseconds as integers everywhere | Matches the desktop `position_ms` and `duration_ms` |
| Subtitle file types | `SUBTITLE_EXTENSIONS` | Which are offered depends on the engine |

## Portable in concept only: the shape must change

| Concept | Desktop | Why it differs on Android |
|---|---|---|
| Media identity | `path_key` from a normalised file path | Android gives `content://` addresses, with no reliable path; the key needs its own definition |
| History | `history` table keyed on `path_key` | Same fields, new key, and a grant that can be lost |
| Bookmarks | `bookmarks` table | Same; depends on the media identity |
| Engine interface | `PlaybackEngine` | The idea carries over. The prototype's `PlayerEngine` is smaller, and surface and lifecycle handling differ |

**History does not sync between devices.** Paths and `content://` addresses don't match across
devices, there's no account, and the plan has no sync feature, so database compatibility isn't a goal.

## Desktop-only: must not be forced onto Android

- `supports_embedding`: a Windows window handle; Android renders to a surface.
- `folders`, library scanning and `VIDEO_EXTENSIONS` as a scan filter: scoped storage does not allow
  reading whole folders without a grant, and the picker filters by type rather than extension.
- `tools/`, `app_log.py` paths, the worker-process design of `ai/`, and the loopback stream proxy:
  each assumes a desktop process model and has not been reviewed for Android.
- Keyboard shortcuts, hover seek previews, and window-based layout.

## How the prototype tested this

One `PlayerEngine` interface served two very different engines without either leaking into the
activity, and the desktop's position-in-milliseconds model worked for both. The damaged-file result
shows why the contract is useful: Media3 raises an error and libVLC reports an immediate end, and
both should reach the UI as `media_open_failed`.

That mapping has been reasoned through, not built. Only the interface itself ran.
