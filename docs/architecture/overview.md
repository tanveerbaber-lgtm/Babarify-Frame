# Babarify Frame — Architecture Overview (M1)

This describes the code as it exists at the end of Milestone 1. The product-level
architecture and roadmap are in the
[plan](../../Babarify_Vision_Official_Architecture_and_Milestones.md).

## Layers and dependency rule

```text
ui/  (PySide6)                 presentation: windows, widgets, theme, Qt thread bridge
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

1. `MainWindow.closeEvent` (M2) must call `PlaybackController.shutdown()` before the
   window is destroyed.
2. Changing or destroying the video widget requires closing (or detaching) the
   engine first.
3. Tests must not let pytest-qt destroy a window that an engine still renders into.

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
