"""Resume rules (M6). Pure functions so the documented tolerances are testable on their own.

* A file is resumed only if at least ``RESUME_MIN_MS`` was watched.
* A file counts as finished when less than ``max(FINISH_MIN_REMAINING_MS, 3 %)`` remains; finished
  files start from the beginning and leave *Continue watching*.
* The player saves the position every ``SAVE_INTERVAL_MS`` while playing and exactly on pause,
  stop, end, opening another file and closing the app. After a normal close the resume point is
  the exact saved position; after a crash it is at most ``SAVE_INTERVAL_MS`` old.
"""

from __future__ import annotations

RESUME_MIN_MS = 10_000
FINISH_MIN_REMAINING_MS = 15_000
FINISH_FRACTION = 0.03
SAVE_INTERVAL_MS = 5_000


def is_finished(position_ms: int, duration_ms: int | None) -> bool:
    if not duration_ms or duration_ms <= 0:
        return False
    return duration_ms - position_ms <= max(FINISH_MIN_REMAINING_MS, duration_ms * FINISH_FRACTION)


def resume_position(position_ms: int, duration_ms: int | None, finished: bool) -> int:
    """Where to start a file that has history: 0 (from the beginning) or the saved position."""
    if finished or position_ms < RESUME_MIN_MS:
        return 0
    if duration_ms and is_finished(position_ms, duration_ms):
        return 0
    return position_ms
