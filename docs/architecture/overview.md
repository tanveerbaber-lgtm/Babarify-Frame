# Babarify Frame — Architecture Overview (M10)

This describes the code as it exists at the end of Milestone 4. The product-level
architecture and roadmap are in the
[plan](../../Babarify_Vision_Official_Architecture_and_Milestones.md).

## Layers and dependency rule

```text
ui/  (PySide6)                 presentation: shell, pages, controls, theme tokens, Qt thread bridge
configuration/                 typed preferences and local JSON store (no Qt)
  │  depends on ↓ only
playback/controller.py         application layer: owns the active engine, survives engine switches
playback/contracts.py          the common playback contract (PlaybackEngine) + EngineBase
playback/lifecycle.py          allowed state transitions and per-command states
playback/factory.py            engine registry with lazy imports and probes
  │
playback/adapters/             mock · libvlc (prototype) · mpv (prototype)
  │                            ONLY this package imports vlc / mpv bindings
core/                          immutable models, error codes, events (no Qt, no engine imports)
```

Rules enforced by structure and review:

1. `ui` never imports an engine binding. It talks to `PlaybackController` / `PlaybackEngine`.
2. `core` imports nothing from `playback` or `ui`.
3. Engine bindings are imported lazily inside the adapter modules, so a missing
   DLL makes that engine *unavailable* instead of breaking start-up.

## Playback contract

`PlaybackEngine` (abstract) exposes `initialize`, `set_video_output`,
`open_media(uri, autoplay)`, `play`, `pause`, `stop`, `seek`, `set_volume`,
`set_muted`, `set_playback_rate`, `get_playback_state`, `get_media_info`,
`get_capabilities`, `subscribe`, `diagnostics`, `close`.

`EngineBase` implements the contract once for every adapter:

- **Validation** — URIs (control characters rejected; local files must exist;
  network schemes rejected until M8), seek bounds, volume `0..max_volume`,
  finite rate within the engine's range, positive window ids.
- **Lifecycle** — commands are checked against `COMMAND_STATES`; adapter-reported
  state changes are checked against `TRANSITIONS`. Invalid engine transitions are
  rejected, logged and recorded in `rejected_transitions` (the benchmark reports them).
- **Events** — `StateChanged`, `PositionChanged`, `MediaInfoChanged`,
  `ErrorOccurred`, `EndReached`. A failing listener never breaks the engine.
- **Cleanup** — `close()` is idempotent, runs adapter cleanup even after errors,
  and always ends in `CLOSED`.

Adapters implement only the `_do_*` hooks plus capabilities and diagnostics.

### States

```text
UNINITIALIZED → READY → LOADING → PLAYING ⇄ PAUSED
                  ↑        │         ↕         │
                  │        │     BUFFERING     │
                  └─ stop ─┴──── ENDED ────────┘
ERROR ← (from any active state) → LOADING / READY
CLOSED ← (from any state; terminal)
```

`stop()` keeps the media selected; `play()` from READY reloads it. `play()` from
ENDED restarts from the beginning.

## Threading

- Public engine methods are called from the UI thread.
- Engines call back on their own threads (libVLC event threads, python-mpv's event
  thread). Adapters never call back into the engine synchronously from a callback;
  follow-up commands go through a single-thread worker per engine.
- `EngineBase` never holds its lock while calling into an engine or a listener,
  which prevents callback deadlocks.
- UI code receives events through `ui.bridge.UiBridge`, a Qt signal that is queued
  onto the UI thread. The shell uses it to report engine probes from a worker thread.
- `EngineBase.close()` drains the deferred-call worker **before** adapter teardown, so
  no deferred call can touch a released engine handle (M1 found this race in both
  adapters).

### Rule: close the engine before its host window

An embedded engine renders into a child window owned by one of its own threads.
Destroying the Qt host window while the engine is still alive can deadlock: the GUI
thread holds the GIL inside `DestroyWindow`, which waits for the engine's window
thread, which is blocked acquiring the GIL inside a Python callback (observed with
libVLC's Direct3D11 output and its log callback; see the benchmark report §6).

Therefore:

1. `MainWindow.closeEvent` calls `PlayerPage.shutdown()` (which shuts the controller down) before the window is
   destroyed (implemented in M2; covered by `test_close_shuts_engine_down_before_window`).
2. Changing or destroying the video widget requires closing (or detaching) the
   engine first.
3. Tests must not let pytest-qt destroy a window that an engine still renders into.

## UI structure (M3)

- `ui/main_window.py` — `MainWindow`, the shell: navigation rail, page stack, menus,
  shortcuts, fullscreen, drag-and-drop, preferences load/save. It owns no playback logic.
- `ui/pages/home.py` (empty state), `ui/pages/player.py` (`PlayerPage`: video, state
  messages, controller wiring), `ui/pages/settings.py` (preferences form).
- `ui/controls.py` — `ControlBar`, a view with signals; responsive breakpoints at 760 and
  540 px hide secondary controls.
- `ui/theme.py` — design tokens (colour, spacing, radius, type) and the stylesheet.
- **Keyboard model:** playback actions are window actions enabled only while Now Playing
  is shown; navigation, open, exit, F1 and Esc are always active.
- **Fullscreen:** the rail, menu and status bar are hidden; the control bar auto-hides
  after the configured delay while playing, detected by polling the cursor position
  (the engine's native window receives the mouse events, not Qt).
- **Preferences:** `configuration.PreferencesStore` validates untrusted JSON, writes
  atomically and quarantines corrupt files. Tests and tools always use temporary stores.

## Player page (M2, now `PlayerPage`)

- `PlayerPage` owns a `PlaybackController` and talks to nothing else in the playback layer.
- The engine is created on a worker thread (`start_engine`) and handed to the controller
  on the UI thread with `PlaybackController.attach()`. A file requested before the engine
  is ready (e.g. from the command line) is opened as soon as it is.
- Engine events (state, media info, errors) are delivered through `UiBridge`. Position is
  **polled** every 100 ms instead of reacting to every engine position event (mpv emits
  one per frame).
- The video area is a native child window (`VideoSurface`) that the engine renders into.
  Text cannot be drawn over a Direct3D child window, so idle, error and audio-only states
  switch a `QStackedWidget` to a message page instead of overlaying the video.
- libVLC's mouse and keyboard handling in its video window is disabled so Qt receives
  double-click (fullscreen) and keyboard shortcuts. Shortcuts are window actions, so they
  keep working in fullscreen while the menu bar is hidden.
- Codec names are normalised to FFmpeg/ffprobe vocabulary by every adapter.

## Engine options and diagnostics (M4)

- `EngineOptions(hardware_decoding=...)` is passed by the factory to the adapter at creation.
  Changing it means creating a new engine; `PlayerPage.restart_engine()` does that and resumes
  the current file at the same position and play/pause state.
- The contract has `diagnostics()` with standard keys (`engine`, `decoder`, `video_output`,
  `log_errors`), `playback_stats()` (frame counters) and `recent_log()`. `decoder` says
  `hardware (<api>)` only when the engine confirmed it, `software` once frames are decoded
  without it, `not decoding yet` or `no video` otherwise.
- libVLC specifics: the hardware option is a **per-media** option (`:avcodec-hw=`), because
  libVLC 3.0.24 ignores it at instance level (R18). All libVLC engines in a process share
  **one libVLC instance** (`_SharedInstance`), because each instance create/release leaks and
  repeated creation eventually crashed `libvlc_new` (R20). The shared log callback fans out
  to the engines currently registered.
- `ui/diagnostics.py` — the Playback info panel (Ctrl+I), built only from the contract.

## Audio and subtitles (M5)

- Contract: `select_audio_track`, `select_subtitle_track` (`None` = off), `add_subtitle_file`,
  `set_audio_delay`, `set_subtitle_delay` (integer ms, **positive = later**, limit
  `max_delay_ms`), `set_subtitle_style`. `EngineBase` validates everything (track ids against
  the current `MediaInfo`, subtitle path: control characters, existence, extension allow-list
  `SUBTITLE_EXTENSIONS`, 20 MB limit) before calling the adapter's optional `_do_*` hook; a hook
  an engine lacks reports `UNSUPPORTED`. Delays reset when a file is opened and appear in
  `PlaybackStatus`.
- Non-fatal problems (an unreadable subtitle file) are a `Notice` event: playback keeps its
  state and the UI shows the message in the status bar.
- `SubtitleStyle` (font, size %, colour, background opacity, named position) is part of
  `EngineOptions`. Capabilities say how it applies: `subtitle_style="live"` (mpv, mock) or
  `"restart"` (libVLC: style is an instance option; `PlayerPage` restarts the engine and
  restores position, play state, selected tracks and delays). Style affects plain-text
  subtitles only; ASS/SSA keep their own styling.
- libVLC specifics (measured in the M5 spike): a newly selected subtitle track or a new
  subtitle delay needs a re-seek to the current time, or lines already read ahead are lost;
  `add_slave` reports success even for unreadable files, so the adapter confirms a new track
  appeared within 2.5 s and otherwise emits a `Notice`; one shared instance exists **per
  style** (style arguments are part of the shared-instance key).
- `ui/subtitles.py` — track labels, the tracks menu (rebuilt each time it opens) and the
  non-modal Sync dialog. Track preferences (preferred audio/subtitle language, show subtitles
  automatically) are applied once per file, when tracks are known.
- Dual subtitles are not offered (`supports_dual_subtitles=False` on all engines).

## Library, history and playlists (M6)

- `library/` is a new layer between `playback` and `ui`: it may use `core` and the
  `playback.media_probe` contract, never the UI.
  - `database.py` — one SQLite file (`%APPDATA%\Babarify\Frame\library.db`) with
    versioned migrations (`PRAGMA user_version`; one transaction each), `quick_check` at start,
    recovery by moving a damaged file aside, and a refusal to touch a newer schema.
  - `scanner.py` — walks only user-chosen folders; skips hidden/system entries, links and
    junctions; unchanged files (size + mtime) are not read; new/changed files get a content key
    (size + SHA-1 of first and last 64 KiB) for duplicate detection.
  - `service.py` — one background worker: scan, then metadata and thumbnails through a
    `MediaProbe`. Events go to listeners on the worker thread (UI uses `UiBridge`). Probing
    pauses between files while a video plays.
  - `history.py` — resume rules (minimum 10 s watched; finished when less than
    max(15 s, 3 %) remains; saved every 5 s and on pause/stop/file change/close).
- `playback/media_probe.py` defines the probe contract; `adapters/libvlc_probe.py` implements
  it with preparsing plus a muted, windowless decode into memory (libVLC 3 has no thumbnail
  API). It uses its own shared libVLC instance (R20 rule: never one instance per file).
- Identity of a file is `path_key` (absolute, case- and separator-normalised); URIs are their
  own key. Files are never deleted or modified by the library: "remove" removes records.
- UI: `pages/library.py` (grid with `library_view.LibraryModel`/`LibraryDelegate`, playlists
  panel, folders dialog), Home's *Continue watching* and *Recently played*, Settings → Privacy
  (remember history, resume, clear). `PlayerPage` owns saving positions and the play queue.

## Picture and sound (M7)

- `core/enhancements.py`: `PictureSettings` (brightness, contrast, saturation, hue, gamma),
  `EqualizerSettings` (on/off, preset name, preamp, 10 bands in dB), `VideoTransform`
  (rotations and flips), `EnhancementProfile`, plus the allowed aspect/crop/zoom values. All
  validate untrusted data like `SubtitleStyle`.
- Contract: `set_picture`, `set_video_geometry(aspect, crop, zoom)`, `set_equalizer`,
  `equalizer_preset(name)`, `set_rotation`, `frame_step(backward)`, `take_snapshot(path)`.
  `EngineBase` refuses (UNSUPPORTED) anything the capabilities do not list, instead of
  silently ignoring it; defaults are always accepted.
- Capabilities say what each engine really does (measured on screen for libVLC):
  `picture_adjustments` (libVLC drops gamma under hardware decoding, where it has no effect),
  `supports_aspect_ratio/crop/zoom`, `rotation` ("live"/"restart"/"unsupported"),
  `supports_equalizer` with the engine's presets and band frequencies,
  `supports_frame_step` / `supports_frame_back_step`, `supports_snapshot`.
- libVLC: rotation is an instance option (`transform` filter), so it is part of the shared
  instance key and a change restarts the engine at the same position (like subtitle style).
  Picture values are always re-applied by switching the adjust filter off and on (R30).
- `PlayerPage` owns per-file geometry (reset on open), session rotation, A-B repeat (checked
  on the 100 ms position poll), frame stepping and snapshots (`Pictures\Babarify Frame`).
  Picture, equalizer and profiles persist in preferences. Volume boost (up to 200 %) is
  opt-in and never remembered.
- `ui/enhancements.py`: the Picture & Sound panel (Ctrl+E), built from capabilities.

## Network streams (M8)

Every address (typed, dropped, from history or inside a playlist) is untrusted.

- `core/network.py` `validate_stream_url`: only http, https and rtsp; a host is required;
  user names/passwords, whitespace and control characters are refused; at most 2,048
  characters; the fragment is dropped. `normalize_local_uri` applies it to every network
  URI, limited to the engine's `allowed_schemes` (`EngineCapabilities.network_schemes`
  tells the UI; mpv has none yet).
- libVLC 3 follows HTTP redirects to *any* scheme it has a plugin for (measured: a redirect
  to `file:///…` played the local file) and HLS manifests may name `file:` segments. So
  libVLC never fetches a web address: `playback/stream_proxy.py` runs a loopback HTTP server
  (127.0.0.1, random port, random per-process path token) that fetches upstream itself
  (system certificate store, connect 10 s / read 20 s), follows at most 5 redirects and
  only to validated http/https addresses, rewrites every `#EXTM3U` playlist entry and
  `URI="…"` attribute to go through it again (other schemes are removed and counted),
  refuses DASH/Smooth manifests (415) and playlists over 4 MB, and records a reason for
  every refusal. libVLC runs with `--no-lua`, so Lua playlist/meta scripts cannot fetch
  pages around the proxy. RTSP goes to libVLC (live555) directly.
- Remote M3U/PLS/XSPF lists end at once in libVLC with their entries as sub-items; the
  adapter plays the first entry that passes `validate_stream_url` (through the proxy),
  skips the rest with a `Notice`, and stops at 3 levels of nesting.
- A server that accepts the connection and never answers leaves libVLC "opening" forever:
  the adapter gives up after `OPEN_TIMEOUT_S` (30 s). Failures are `NETWORK_ERROR` with the
  proxy's reason ("the server answered 404 …", "redirected to a non-web address (file:)").
- UI: *File → Open network stream* (Ctrl+N) checks the address while typing and lists recent
  streams from history; links dropped from a browser open the same way. Titles, history
  names and the media panel show host and file name, never the query string.

## Chapters, bookmarks, media information and previews (M8)

- `MediaInfo.chapters` (`Chapter(index, start_ms, title)`) and `MediaInfo.metadata` (file
  tags); `TrackInfo` carries size, frame rate, channels, sample rate and bitrate when the
  engine reports them. libVLC chapters are read with ctypes (`read_chapters`): python-vlc's
  helper never frees libVLC's array. Chapter navigation is a seek; *previous* restarts the
  current chapter when more than 3 s into it.
- Bookmarks: library schema v3 `bookmarks` table, per file by `path_key` like history, at
  most 200 per file, labels cleaned to 120 characters. They are the user's notes, so
  clearing or switching off history keeps them.
- Seek-bar previews: `playback/preview.py` `FramePreview`; `LibVlcPreview` is a second,
  muted, windowless player paused on the file (software decoding, memory callbacks, the
  probe's shared instance, R20/R26) that seeks for each request. `ui/seek_preview.py` runs it
  on one background thread, decodes only the newest request and caches up to 400 frames per
  file. Local video files only (a stream would be downloaded twice); *Settings → Playback*
  can switch it off. The seek bar draws chapter starts (grey) and bookmarks (amber).
- `ui/media_info.py` (Ctrl+Shift+I): general facts, tags, every track and the chapters;
  values are HTML-escaped and shortened, and can be copied as text.

## Local AI: generated subtitles and spoken-word search (M9)

Off until *Settings → AI features* is switched on; local only (owner decision).

- `ai/models.py`: the speech models (faster-whisper conversions of Whisper, MIT), each pinned
  to a Hugging Face revision with the size and SHA-256 of every file. Models live in
  `%LOCALAPPDATA%\Babarify\Frame\models` (`BABARIFY_MODELS_DIR`). A model is downloaded only
  after the user confirms a dialog naming its size, source, revision and licence; files go to a
  staging folder and are installed only if every checksum matches.
- `ai/worker.py` runs as its own process (`python -m babarify_frame.ai.worker`) at
  below-normal priority with half the cores, so the speech engine (CTranslate2, onnxruntime)
  can neither crash nor slow playback; Cancel ends the process. It decodes the audio with
  libVLC (transcode to 16 kHz mono WAV: no second media parser, about 200× real time), runs
  faster-whisper offline (`HF_HUB_OFFLINE`) with the voice-activity filter and word timings,
  and reports JSON lines (stage, progress, language, done/error). PyAV, which faster-whisper
  would use for decoding, is never called (its current version is incompatible anyway).
- `ai/subtitles.py`: cues rebuilt from word timings (sentence ends, ≤ 84 characters, ≤ 7 s,
  pauses over 0.7 s, two lines, no overlap), SRT output, file names
  `<name>.<language>.machine-generated.srt` in `<config>\subtitles\<hash of path_key>\`,
  never next to the media.
- Library schema v4: `transcripts` (one per file) and the FTS5 table `transcript_cues`.
  `search_spoken` reduces the query to quoted words (prefix match on the last), so FTS syntax
  typed by the user has no effect. *Delete all generated subtitles* removes files and index.
- UI (`ui/ai.py`): *Audio & Subtitles → Generate subtitles (local AI)* (Ctrl+Shift+G) with
  language (or automatic detection), model, time estimate, progress and Stop; the result is
  added to the subtitle tracks. *View → Search spoken words* (Ctrl+Shift+F) opens a result
  1 s before the words. Switching AI off hides both and stops a running job.

## Packaging and release (M10)

- Release layout (per-user install, `%LOCALAPPDATA%\Programs\Babarify Frame`):
  `Babarify Frame.exe` and `_internal\` (PyInstaller; Python, Qt/PySide6 as separate DLLs),
  `engines\vlc\` (curated libVLC: 259 of 360 plugins, `tools/vlc_plugins.py`), and the optional
  `ai\babarify-ai-worker.exe` (+ its own `_internal`), plus licence, notices and privacy texts.
- A frozen app loads libVLC only from its own `engines` folder (`_engine_paths.bundled_dir`):
  `BABARIFY_VLC_DIR` is ignored, and mpv is never loaded. The worker finds the engine one level
  up.
- `app_log.py`: local `app.log` (rotating) and `crash.log` (`faulthandler` and unhandled
  Python errors) in `%LOCALAPPDATA%\Babarify\Frame\logs`; nothing is uploaded. Engine
  start-up time and failures are logged.
- Labels that show untrusted text use plain text (`widgets.plain_text`, R44).
- Build, versioning, update/rollback, signing and licence obligations: [RELEASING.md](../RELEASING.md).

## Capability reporting

`EngineCapabilities` states what an engine supports (seek, rate range, maximum
volume, track selection, window embedding, hardware decoding *requested*). The UI
must disable or explain anything reported unsupported. Hardware decoding that is
actually in use is reported per media via `diagnostics()["hwdec"]`, never assumed.

## Engine discovery (development)

Adapters look for engines in `BABARIFY_VLC_DIR` / `BABARIFY_MPV_DIR`, then in the
git-ignored `.engines/` folder. Packaging (M10) will bundle the selected engine.

## Deviations from the proposed repository layout

The plan proposes `apps/desktop-windows/` plus several `packages/*` with hyphenated
names. M1 uses one importable package (`src/babarify_frame/` with `core`, `playback`,
`ui` subpackages) because:

- hyphenated directories cannot be Python import names;
- one distribution keeps editable installs, mypy and packaging simple while there
  is a single app;
- the layer boundaries are the same, and can be split into separate distributions
  when a second client (mobile, M12+) actually needs to share code.
