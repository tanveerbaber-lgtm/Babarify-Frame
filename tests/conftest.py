from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

from babarify_frame.core.events import PlaybackEvent
from babarify_frame.playback.adapters.mock import MockEngine

# The app's own log (M10) goes to a throw-away folder in tests, never the user's log folder;
# set before any test starts the app, so subprocesses inherit it.
os.environ.setdefault("BABARIFY_LOG_DIR", tempfile.mkdtemp(prefix="babarify-test-logs-"))


@pytest.fixture
def engine() -> Iterator[MockEngine]:
    eng = MockEngine()
    eng.initialize()
    yield eng
    eng.close()


@pytest.fixture
def events(engine: MockEngine) -> list[PlaybackEvent]:
    received: list[PlaybackEvent] = []
    engine.subscribe(received.append)
    return received
