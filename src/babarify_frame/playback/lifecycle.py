"""Playback lifecycle rules: which state transitions and commands are allowed."""

from __future__ import annotations

from babarify_frame.core.models import PlaybackState as S

# Allowed engine state transitions. Anything else is a bug in an adapter or an
# unexpected engine event sequence, and is rejected by ``EngineBase``.
TRANSITIONS: dict[S, frozenset[S]] = {
    S.UNINITIALIZED: frozenset({S.READY, S.ERROR, S.CLOSED}),
    S.READY: frozenset({S.LOADING, S.ERROR, S.CLOSED}),
    S.LOADING: frozenset({S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING, S.ERROR, S.READY, S.CLOSED}),
    S.PLAYING: frozenset({S.PAUSED, S.BUFFERING, S.ENDED, S.ERROR, S.READY, S.LOADING, S.CLOSED}),
    S.PAUSED: frozenset({S.PLAYING, S.BUFFERING, S.ENDED, S.ERROR, S.READY, S.LOADING, S.CLOSED}),
    S.BUFFERING: frozenset({S.PLAYING, S.PAUSED, S.ENDED, S.ERROR, S.READY, S.LOADING, S.CLOSED}),
    S.ENDED: frozenset({S.PLAYING, S.PAUSED, S.LOADING, S.READY, S.ERROR, S.CLOSED}),
    S.ERROR: frozenset({S.LOADING, S.READY, S.CLOSED}),
    S.CLOSED: frozenset(),
}

_ACTIVE = frozenset({S.READY, S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED, S.ERROR})

# States in which each public command may be issued.
COMMAND_STATES: dict[str, frozenset[S]] = {
    "open_media": _ACTIVE,
    "play": frozenset({S.READY, S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED}),
    "pause": frozenset({S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING}),
    "stop": _ACTIVE,
    "seek": frozenset({S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED}),
    "set_volume": _ACTIVE,
    "set_muted": _ACTIVE,
    "set_playback_rate": _ACTIVE,
    "select_track": frozenset({S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED}),
    "set_delay": frozenset({S.LOADING, S.PLAYING, S.PAUSED, S.BUFFERING, S.ENDED}),
    "set_subtitle_style": _ACTIVE,
    "set_picture": _ACTIVE,
    "set_video_geometry": _ACTIVE,
    "set_equalizer": _ACTIVE,
    "set_rotation": _ACTIVE,
    "frame_step": frozenset({S.PLAYING, S.PAUSED}),
    "take_snapshot": frozenset({S.PLAYING, S.PAUSED, S.BUFFERING}),
}


def can_transition(old: S, new: S) -> bool:
    return new in TRANSITIONS[old]


def command_allowed(command: str, state: S) -> bool:
    return state in COMMAND_STATES[command]
