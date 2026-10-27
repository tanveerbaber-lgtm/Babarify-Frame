import pytest

from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.lifecycle import COMMAND_STATES, TRANSITIONS, can_transition, command_allowed


def test_every_state_has_transition_rules() -> None:
    assert set(TRANSITIONS) == set(S)


def test_closed_is_terminal() -> None:
    assert TRANSITIONS[S.CLOSED] == frozenset()
    for state in S:
        if state is not S.CLOSED:
            assert can_transition(state, S.CLOSED), state


def test_cannot_skip_initialisation() -> None:
    assert not can_transition(S.UNINITIALIZED, S.PLAYING)
    assert not can_transition(S.UNINITIALIZED, S.LOADING)


def test_ready_must_load_before_playing() -> None:
    assert not can_transition(S.READY, S.PLAYING)
    assert can_transition(S.READY, S.LOADING)


def test_error_recovers_only_by_loading_resetting_or_closing() -> None:
    assert TRANSITIONS[S.ERROR] == frozenset({S.LOADING, S.READY, S.CLOSED})


@pytest.mark.parametrize("command", sorted(COMMAND_STATES))
def test_no_command_allowed_when_closed_or_uninitialised(command: str) -> None:
    assert not command_allowed(command, S.CLOSED)
    assert not command_allowed(command, S.UNINITIALIZED)


def test_seek_requires_loaded_media() -> None:
    assert not command_allowed("seek", S.READY)
    assert not command_allowed("seek", S.LOADING)
    assert not command_allowed("seek", S.ERROR)
    assert command_allowed("seek", S.PAUSED)
