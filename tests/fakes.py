"""Test doubles shared by unit and UI tests."""

from __future__ import annotations

import threading
import time

from babarify_frame.playback.media_probe import MediaProbe, ProbeResult


class FakeProbe(MediaProbe):
    """Deterministic probe: videos get a 32x18 thumbnail, .flac is audio, 'broken' is unreadable."""

    name = "fake"

    def __init__(self, delay_s: float = 0.0) -> None:
        self.delay_s = delay_s
        self.probed: list[str] = []
        self.closed = False

    def probe(self, path: str, cancel: threading.Event) -> ProbeResult | None:
        if self.delay_s:
            cancel.wait(self.delay_s)
        if cancel.is_set():
            return None
        self.probed.append(path)
        if "broken" in path:
            return None
        if path.lower().endswith(".flac"):
            return ProbeResult(180_000, None, None, None, "flac")
        w, h = 32, 18
        return ProbeResult(600_000, 1920, 1080, "h264", "aac", b"\x80\x40\x20\x00" * (w * h), w, h)

    def close(self) -> None:
        self.closed = True


def wait_for(check, timeout: float = 5.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return bool(check())
