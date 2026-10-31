"""M6 library service: background scan + metadata, thumbnails, cancel, events."""

from __future__ import annotations

from pathlib import Path

from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.service import (
    LibraryEvent,
    LibraryService,
    MetadataUpdated,
    ScanFinished,
    WorkerIdle,
)
from fakes import FakeProbe, wait_for

CLIP = b"\x00" * 64


def make(
    tmp_path: Path, probe: FakeProbe | None = None
) -> tuple[LibraryService, FakeProbe, list[LibraryEvent]]:
    probe = probe or FakeProbe()
    service = LibraryService(LibraryDatabase(None), lambda: probe, tmp_path / "thumbs")
    events: list[LibraryEvent] = []
    service.add_listener(events.append)
    return service, probe, events


def test_scan_then_metadata_and_thumbnails(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    for name in ("a.mp4", "b.mkv", "song.flac", "broken.mp4"):
        (media / name).write_bytes(CLIP + name.encode())
    service, probe, events = make(tmp_path)
    service.db.add_folder(str(media))
    service.scan()
    assert service.wait_idle(10)
    assert sorted(Path(p).name for p in probe.probed) == ["a.mp4", "b.mkv", "broken.mp4", "song.flac"]
    by_name = {m.name: m for m in service.db.media()}
    assert by_name["a.mp4"].video_codec == "h264" and by_name["a.mp4"].thumbnail
    thumb = service.thumbnail_path(by_name["a.mp4"].thumbnail)
    assert thumb is not None and thumb.is_file() and thumb.stat().st_size > 0
    assert by_name["song.flac"].audio_codec == "flac" and by_name["song.flac"].thumbnail is None
    assert by_name["broken.mp4"].probed and by_name["broken.mp4"].duration_ms is None  # kept, no details
    kinds = [type(e) for e in events]
    assert ScanFinished in kinds and MetadataUpdated in kinds and kinds[-1] is WorkerIdle
    service.shutdown()
    assert probe.closed


def test_metadata_is_not_read_twice(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(CLIP)
    service, probe, _ = make(tmp_path)
    service.db.add_folder(str(tmp_path))
    service.scan()
    assert service.wait_idle(10)
    service.scan()
    assert service.wait_idle(10)
    assert len(probe.probed) == 1
    service.shutdown()


def test_cancel_stops_probing_and_keeps_work(tmp_path: Path) -> None:
    for i in range(30):
        (tmp_path / f"{i:02d}.mp4").write_bytes(CLIP + bytes([i]))
    service, probe, _ = make(tmp_path, FakeProbe(delay_s=0.05))
    service.db.add_folder(str(tmp_path))
    service.scan()
    assert wait_for(lambda: len(probe.probed) >= 2)
    service.cancel()
    assert service.wait_idle(5)
    total, _missing, pending = service.db.counts()
    assert total == 30 and 0 < pending < 30  # what was done is kept; the rest waits
    service.fetch_metadata()
    assert service.wait_idle(10)
    assert service.db.counts()[2] == 0
    service.shutdown()


def test_orphan_thumbnails_are_removed(tmp_path: Path) -> None:
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "a.mp4").write_bytes(CLIP)
    service, _probe, _ = make(tmp_path)
    service.db.add_folder(str(tmp_path / "media"))
    service.scan()
    assert service.wait_idle(10)
    stray = tmp_path / "thumbs" / "stray.jpg"
    stray.write_bytes(b"x")
    service.db.remove_media([m.id for m in service.db.media()])
    service.fetch_metadata()
    assert service.wait_idle(10)
    assert not stray.exists() and not list((tmp_path / "thumbs").glob("*.jpg"))
    service.shutdown()


def test_missing_engine_leaves_library_working(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(CLIP)

    def no_engine() -> FakeProbe:
        raise OSError("libvlc.dll not found")

    service = LibraryService(LibraryDatabase(None), no_engine, tmp_path / "thumbs")
    service.db.add_folder(str(tmp_path))
    service.scan()
    assert service.wait_idle(10)
    assert [m.name for m in service.db.media()] == ["a.mp4"]
    service.shutdown()


def test_stored_thumbnail_names_cannot_escape_the_folder(tmp_path: Path) -> None:
    service, _probe, _ = make(tmp_path)
    path = service.thumbnail_path("..\\..\\Windows\\win.ini")
    assert path is not None and path.parent == tmp_path / "thumbs"
    service.shutdown()
