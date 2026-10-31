"""M6 real-engine tests: libVLC media probe over the corpus, and resume accuracy with real playback.

Resume tolerance (documented in docs/milestones/M6): after a normal stop or close the file
resumes within RESUME_TOLERANCE_MS of the saved position. libVLC seeks to the requested time
(not only to keyframes) for these containers; the tolerance covers decoder start-up.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.factory import default_factory
from babarify_frame.ui.app import load_icon
from babarify_frame.ui.main_window import MainWindow

pytestmark = [pytest.mark.integration, pytest.mark.ui]

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated"
MANIFEST = ROOT / "tools" / "engine-benchmark" / "media-manifest.json"
LONG = MEDIA / "e_long_1h_240p.mkv"
RESUME_TOLERANCE_MS = 1_000

_probe = default_factory().probe("libvlc")
requires_libvlc = pytest.mark.skipif(not _probe.available, reason=f"libvlc unavailable: {_probe.detail}")


def _corpus(kind: str) -> list[Any]:
    if not MANIFEST.exists():
        return []
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    return [pytest.param(e, id=e["file"]) for e in entries if e["kind"] == kind]


@pytest.fixture(scope="module")
def probe() -> Iterator[Any]:
    if not _probe.available:
        pytest.skip("libvlc unavailable")
    from babarify_frame.playback.adapters.libvlc_probe import LibVlcProbe

    p = LibVlcProbe()
    yield p
    p.close()


@requires_libvlc
@pytest.mark.parametrize("media", _corpus("valid"))
def test_probe_reads_corpus_file(probe: Any, media: dict[str, Any]) -> None:
    expect = media["expect"]
    started = time.perf_counter()
    result = probe.probe(str(MEDIA / media["file"]), threading.Event())
    elapsed = time.perf_counter() - started
    assert result is not None
    assert result.duration_ms and result.duration_ms > 0
    if "video" in expect:
        assert (result.width, result.height) == (expect["width"], expect["height"]) or media["file"].endswith(
            (".mpg", ".ts")
        )  # MPEG-PS/TS dimensions may include padding or come from the decoder
        if result.thumbnail is not None:
            assert len(result.thumbnail) == result.thumbnail_width * result.thumbnail_height * 4
            assert result.thumbnail_width <= 320
    else:
        assert result.thumbnail is None and result.video_codec is None
        assert result.audio_codec == expect["audio"]
    assert elapsed < 6.0


@requires_libvlc
def test_probe_thumbnails_most_videos(probe: Any) -> None:
    videos = [p.values[0] for p in _corpus("valid") if "video" in p.values[0]["expect"]]
    with_thumb = 0
    for media in videos:
        result = probe.probe(str(MEDIA / media["file"]), threading.Event())
        with_thumb += bool(result and result.thumbnail)
    assert with_thumb >= len(videos) - 2, f"{with_thumb} of {len(videos)}"


@requires_libvlc
@pytest.mark.parametrize("media", _corpus("invalid"))
def test_probe_rejects_invalid_files_quickly(probe: Any, media: dict[str, Any]) -> None:
    started = time.perf_counter()
    result = probe.probe(str(MEDIA / media["file"]), threading.Event())
    assert result is None or result.thumbnail is None
    assert time.perf_counter() - started < 10.0


@requires_libvlc
def test_probe_can_be_cancelled(probe: Any) -> None:
    cancel = threading.Event()
    cancel.set()
    started = time.perf_counter()
    assert probe.probe(str(LONG), cancel) is None
    assert time.perf_counter() - started < 1.0


def _window(qtbot: QtBot, tmp_path: Path, db_path: Path) -> MainWindow:
    service = LibraryService(LibraryDatabase(db_path))
    win = MainWindow(
        default_factory(),
        load_icon(),
        engine_name="libvlc",
        store=PreferencesStore(tmp_path / "settings.json"),
        library=service,
    )
    win.show()
    win.resize(800, 500)
    win.start_engine()
    qtbot.waitUntil(lambda: win.player.engine_is_ready, timeout=15_000)
    return win


@requires_libvlc
@pytest.mark.parametrize("target_s", [95, 1_800, 3_300])
def test_resume_is_accurate_across_app_restarts(qtbot: QtBot, tmp_path: Path, target_s: int) -> None:
    if not LONG.exists():
        pytest.skip("generated media missing")
    db_path = tmp_path / "library.db"
    win = _window(qtbot, tmp_path, db_path)
    win.open_path(str(LONG))
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=15_000)
    win.player.seek_to(target_s * 1000)
    qtbot.waitUntil(lambda: win.controller.status().position_ms >= target_s * 1000 + 1500, timeout=15_000)
    win.close()  # saves the exact position, closes the engine before the window
    saved = LibraryDatabase(db_path).history_for(str(LONG))
    assert saved is not None and saved.position_ms >= target_s * 1000

    win = _window(qtbot, tmp_path, db_path)
    win.open_path(str(LONG))
    qtbot.waitUntil(lambda: win.player.state is S.PLAYING, timeout=15_000)
    # While a seek is pending the engine reports the requested target (R12/R21), so the target
    # itself proves nothing. Wait for the first real time report after the jump: that is where
    # playback actually continues (plus at most one time-report interval of playing).
    qtbot.waitUntil(
        lambda: win.controller.status().position_ms not in (0, saved.position_ms)
        and win.controller.status().position_ms > saved.position_ms - 60_000,
        timeout=15_000,
    )
    first = win.controller.status().position_ms
    error = first - saved.position_ms
    print(f"resume {target_s}s: saved {saved.position_ms} ms, first real {first} ms, error {error:+d} ms")
    assert -RESUME_TOLERANCE_MS <= error <= RESUME_TOLERANCE_MS
    win.close()
