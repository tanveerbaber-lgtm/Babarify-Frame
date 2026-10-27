from __future__ import annotations

from collections.abc import Iterator

import pytest

from babarify_frame.core.events import PlaybackEvent
from babarify_frame.playback.adapters.mock import MockEngine


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
