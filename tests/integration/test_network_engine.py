"""M8 with real libVLC: network streams through the proxy, chapters, tags and seek previews.

Media is generated with ffmpeg into a temporary folder and served by ``netserver`` on
127.0.0.1 (Range requests supported, like real web servers). Nothing leaves this machine.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

import babarify_frame.playback.adapters.libvlc as libvlc_adapter
from babarify_frame.core.errors import ErrorCode
from babarify_frame.core.events import ErrorOccurred, Notice, PlaybackEvent
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.core.models import TrackKind
from babarify_frame.playback.contracts import PlaybackEngine
from babarify_frame.playback.factory import default_factory
from netserver import LocalServer

pytestmark = [pytest.mark.integration, pytest.mark.ui]

ROOT = Path(__file__).resolve().parents[2]
H264 = ROOT / "tests" / "fixtures" / "media" / "generated" / "h264_1080p30_aac.mp4"
TIMEOUT_MS = 15_000
_probe = default_factory().probe("libvlc")
requires_libvlc = pytest.mark.skipif(not _probe.available, reason=f"libVLC unavailable: {_probe.detail}")


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is needed to make test media")
    root = tmp_path_factory.mktemp("m8-media")
    meta = root / "meta.txt"
    meta.write_text(
        ";FFMETADATA1\ntitle=M8 Test Title\nartist=M8 Artist\ngenre=Test\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=4000\ntitle=Opening\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=4000\nEND=9000\ntitle=Middle part\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=9000\nEND=12000\ntitle=End\n",
        encoding="utf-8",
    )
    source = ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=12",
              "-f", "lavfi", "-i", "sine=frequency=440:duration=12:sample_rate=48000"]  # fmt: skip
    _ffmpeg(*source, "-i", str(meta), "-map_metadata", "2", "-map_chapters", "2",
            "-c:v", "libx264", "-g", "25", "-c:a", "aac", "-ac", "2", str(root / "chapters.mkv"))  # fmt: skip
    (root / "hls").mkdir()
    _ffmpeg(*source, "-c:v", "libx264", "-g", "50", "-c:a", "aac", "-hls_time", "2",
            "-hls_playlist_type", "vod", str(root / "hls" / "index.m3u8"))  # fmt: skip
    (root / "secret.mkv").write_bytes((root / "chapters.mkv").read_bytes())  # a "local file" target
    return root


@pytest.fixture(scope="module")
def server(media: Path) -> Iterator[LocalServer]:
    srv = LocalServer(media)
    yield srv
    srv.close()


@pytest.fixture
def engine(qtbot: QtBot) -> Iterator[PlaybackEngine]:
    # Not registered with qtbot: close the engine before its host window (deadlock rule S2).
    window = QWidget()
    window.resize(480, 270)
    window.show()
    eng = default_factory().create("libvlc")
    eng.set_video_output(int(window.winId()))
    yield eng
    eng.close()
    window.close()
    window.deleteLater()


def events_of(engine: PlaybackEngine) -> list[PlaybackEvent]:
    events: list[PlaybackEvent] = []
    engine.subscribe(events.append)
    return events


def plays(qtbot: QtBot, engine: PlaybackEngine, beyond_ms: int = 1500) -> None:
    qtbot.waitUntil(lambda: engine.get_playback_state().position_ms > beyond_ms, timeout=TIMEOUT_MS)
    assert engine.get_playback_state().state in (S.PLAYING, S.BUFFERING)


def fails(
    qtbot: QtBot, engine: PlaybackEngine, events: list[PlaybackEvent], timeout: int = TIMEOUT_MS
) -> str:
    qtbot.waitUntil(lambda: engine.get_playback_state().state is S.ERROR, timeout=timeout)
    errors = [e.error for e in events if isinstance(e, ErrorOccurred)]
    assert errors and errors[-1].code is ErrorCode.NETWORK_ERROR
    assert engine.get_playback_state().position_ms == 0  # nothing was played
    return errors[-1].detail


# ------------------------------------------------------------ streams that play
@requires_libvlc
def test_http_file_plays_seeks_and_has_chapters(
    qtbot: QtBot, engine: PlaybackEngine, server: LocalServer
) -> None:
    engine.open_media(server.url("chapters.mkv"))
    plays(qtbot, engine, 800)
    engine.seek(9500)
    qtbot.waitUntil(lambda: engine.get_playback_state().position_ms > 9600, timeout=TIMEOUT_MS)
    info = engine.get_media_info()
    assert info is not None and [c.title for c in info.chapters] == ["Opening", "Middle part", "End"]
    assert any("Range" in r or r.startswith("/chapters.mkv") for r in server.requests)


@requires_libvlc
def test_hls_plays_through_the_proxy(qtbot: QtBot, engine: PlaybackEngine, server: LocalServer) -> None:
    engine.open_media(server.url("hls/index.m3u8"))
    plays(qtbot, engine)
    segments = [r for r in server.requests if r.startswith("/hls/index") and r.endswith(".ts")]
    assert segments  # libVLC fetched the segments, through the proxy (it only knows the proxy address)
    caps = engine.get_capabilities()
    assert caps.network_schemes == frozenset({"http", "https", "rtsp"})


@requires_libvlc
def test_playlist_skips_local_and_vlc_entries(
    qtbot: QtBot, engine: PlaybackEngine, server: LocalServer, media: Path
) -> None:
    events = events_of(engine)
    body = f"#EXTM3U\n{(media / 'secret.mkv').as_uri()}\nvlc://quit\n{server.url('chapters.mkv')}\n"
    engine.open_media(server.url("text?body=" + quote(body, safe="")))
    plays(qtbot, engine, 800)
    notices = [e.message for e in events if isinstance(e, Notice)]
    assert any("skipped 2 playlist entries" in n for n in notices)
    assert not any(r.startswith("/secret") for r in server.requests)  # never fetched, even over http


# ------------------------------------------------------------ refused or failing streams
@requires_libvlc
def test_redirect_to_a_local_file_is_refused(
    qtbot: QtBot, engine: PlaybackEngine, server: LocalServer, media: Path
) -> None:
    """The M8 spike's finding: plain libVLC played the local file here."""
    events = events_of(engine)
    target = quote((media / "secret.mkv").as_uri(), safe="")
    engine.open_media(server.url(f"redirect?to={target}"))
    detail = fails(qtbot, engine, events)
    assert "non-web address (file:)" in detail
    assert engine.get_media_info() is None or not engine.get_media_info().tracks  # type: ignore[union-attr]


@requires_libvlc
def test_hls_with_a_local_file_segment_is_refused(
    qtbot: QtBot, engine: PlaybackEngine, server: LocalServer, media: Path
) -> None:
    events = events_of(engine)
    body = (
        f"#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\n{(media / 'secret.mkv').as_uri()}\n#EXT-X-ENDLIST\n"
    )
    engine.open_media(server.url("text?body=" + quote(body, safe="")))
    assert "not web addresses" in fails(qtbot, engine, events)


@requires_libvlc
@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("missing.mp4", "404"),
        ("text?body=" + quote("this is not media", safe=""), "playable media"),
        ("text?body=" + quote('<?xml version="1.0"?><MPD></MPD>', safe=""), "DASH"),
    ],
)
def test_failures_are_reported_quickly(
    qtbot: QtBot, engine: PlaybackEngine, server: LocalServer, path: str, words: str
) -> None:
    events = events_of(engine)
    started = time.monotonic()
    engine.open_media(server.url(path))
    assert words in fails(qtbot, engine, events)
    assert time.monotonic() - started < 10


@requires_libvlc
def test_unknown_host_and_closed_port(qtbot: QtBot, engine: PlaybackEngine) -> None:
    events = events_of(engine)
    engine.open_media("http://does-not-exist.invalid/a.mp4")
    assert "could not be found" in fails(qtbot, engine, events)
    engine.open_media("rtsp://127.0.0.1:9/stream")  # rtsp goes to libVLC directly
    qtbot.waitUntil(lambda: engine.get_playback_state().state is S.ERROR, timeout=TIMEOUT_MS)


@requires_libvlc
def test_stalled_server_ends_with_a_timeout(
    qtbot: QtBot, engine: PlaybackEngine, server: LocalServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(libvlc_adapter, "OPEN_TIMEOUT_S", 3.0)
    events = events_of(engine)
    engine.open_media(server.url("stall"))
    assert "nothing played within 3 s" in fails(qtbot, engine, events, timeout=10_000)
    # The engine is usable afterwards.
    engine.open_media(server.url("chapters.mkv"))
    plays(qtbot, engine, 500)


@requires_libvlc
def test_local_playback_still_works_after_streams(
    qtbot: QtBot, engine: PlaybackEngine, server: LocalServer
) -> None:
    engine.open_media(server.url("missing.mp4"))
    qtbot.waitUntil(lambda: engine.get_playback_state().state is S.ERROR, timeout=TIMEOUT_MS)
    if not H264.exists():
        pytest.skip("generated media missing")
    engine.open_media(str(H264))
    plays(qtbot, engine)


# ------------------------------------------------------------ chapters, tags, details (local)
@requires_libvlc
def test_local_chapters_tags_and_track_details(qtbot: QtBot, engine: PlaybackEngine, media: Path) -> None:
    engine.open_media(str(media / "chapters.mkv"))
    plays(qtbot, engine, 500)
    qtbot.waitUntil(
        lambda: bool(engine.get_media_info() and engine.get_media_info().chapters), timeout=TIMEOUT_MS
    )  # type: ignore[union-attr]
    info = engine.get_media_info()
    assert info is not None
    assert [(c.start_ms, c.title) for c in info.chapters] == [
        (0, "Opening"),
        (4000, "Middle part"),
        (9000, "End"),
    ]
    tags = dict(info.metadata)
    assert tags.get("Title") == "M8 Test Title" and tags.get("Genre") == "Test"
    video, audio = info.tracks_of(TrackKind.VIDEO)[0], info.tracks_of(TrackKind.AUDIO)[0]
    assert (video.width, video.height, round(video.frame_rate)) == (640, 360, 25)
    assert (audio.channels, audio.sample_rate) == (2, 48000)
    engine.seek(info.chapters[2].start_ms)  # chapter navigation is a seek to the chapter start
    qtbot.waitUntil(lambda: engine.get_playback_state().position_ms >= 9000, timeout=TIMEOUT_MS)


# ------------------------------------------------------------ seek previews
@requires_libvlc
def test_previews_are_real_frames_and_do_not_disturb_playback(qtbot: QtBot, engine: PlaybackEngine) -> None:
    if not H264.exists():
        pytest.skip("generated media missing")
    from babarify_frame.playback.adapters.libvlc_preview import LibVlcPreview

    engine.open_media(str(H264))
    plays(qtbot, engine, 500)
    preview = LibVlcPreview()
    try:
        assert preview.open(str(H264))
        frames = {}
        for ms in (1000, 6000, 1000, 9000):
            started = time.monotonic()
            frame = preview.frame_at(ms)
            assert frame is not None and frame.width == 192 and frame.height == 108
            assert time.monotonic() - started < 2.0
            frames.setdefault(ms, frame.data)
        # Different times give different pictures (the test clip has a running timecode).
        assert frames[1000] != frames[6000] != frames[9000]
        before = engine.get_playback_state().position_ms
        time.sleep(0.6)
        assert engine.get_playback_state().position_ms > before  # main playback kept going
        assert engine.get_playback_state().state is S.PLAYING
    finally:
        preview.close()
    assert not preview.open(str(H264.with_name("not_media.mp4")))  # no picture: False, no hang
