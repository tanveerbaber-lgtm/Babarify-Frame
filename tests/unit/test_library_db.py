"""M6 library database: migrations, recovery, folders, scanning, duplicates, history, playlists."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from babarify_frame.library import database as dbmod
from babarify_frame.library.database import SCHEMA_VERSION, LibraryDatabase, LibraryError
from babarify_frame.library.history import RESUME_MIN_MS, is_finished, resume_position
from babarify_frame.library.models import SortOrder, path_key
from babarify_frame.library.scanner import scan_folder

CLIP = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 8


def touch(path: Path, data: bytes = CLIP) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def db() -> LibraryDatabase:
    return LibraryDatabase(None)


def scan(db: LibraryDatabase, folder_path: Path, cancel: threading.Event | None = None):  # type: ignore[no-untyped-def]
    folder = next(f for f in db.folders() if Path(f.path) == folder_path.resolve())
    return scan_folder(db, folder, cancel or threading.Event())


# ------------------------------------------------------------ migrations
def test_fresh_database_has_current_schema(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.db")
    assert db.schema_version == SCHEMA_VERSION == 3
    assert db.recovered is None and db.read_only_reason is None
    db.close()


def test_version_1_database_migrates_and_keeps_data(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    conn = sqlite3.connect(path, isolation_level=None)
    LibraryDatabase._migrate(conn, target=1)
    conn.execute(
        "INSERT INTO history(path_key, path, title, position_ms, duration_ms, play_count, last_played_at) "
        "VALUES ('k', 'C:/a.mkv', 'a.mkv', 42000, 600000, 3, 1.0)"
    )
    conn.close()
    db = LibraryDatabase(path)
    assert db.schema_version == 3
    row = db._query("SELECT position_ms, play_count FROM history WHERE path_key = 'k'")[0]
    assert (row[0], row[1]) == (42000, 3)
    assert db.playlists() == []  # the v2 tables exist
    assert db.bookmarks_for("C:/a.mkv") == []  # and the v3 table
    db.close()


def test_failed_migration_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "library.db"
    LibraryDatabase(path).close()
    monkeypatch.setattr(dbmod, "MIGRATIONS", (*dbmod.MIGRATIONS, ("CREATE TABLE extra(x)", "NOT VALID SQL")))
    conn = sqlite3.connect(path, isolation_level=None)
    with pytest.raises(sqlite3.OperationalError):
        LibraryDatabase._migrate(conn, target=4)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'extra'").fetchone() is None
    conn.close()


# -------------------------------------------------------------- recovery
@pytest.mark.parametrize("content", [b"this is not a database at all" * 100, b""])
def test_garbage_file_is_moved_aside_and_replaced(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "library.db"
    path.write_bytes(content or b"\xff" * 4096)
    db = LibraryDatabase(path)
    assert db.recovered is not None and "damaged" in db.recovered
    assert db.schema_version == SCHEMA_VERSION
    kept = list(tmp_path.glob("library.corrupt-*.db"))
    assert len(kept) == 1
    db.close()


def test_database_with_damaged_pages_is_recovered(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    db = LibraryDatabase(path)
    for i in range(400):
        db.save_position(f"C:/videos/file{i:04d}.mkv", f"file{i}", 20_000, 600_000)
    db._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()
    data = bytearray(path.read_bytes())
    assert len(data) > 16_384
    data[8192:12288] = b"\xa5" * 4096  # overwrite a b-tree page
    path.write_bytes(bytes(data))
    recovered = LibraryDatabase(path)
    assert recovered.recovered is not None
    assert recovered.history_count() == 0  # a fresh database
    recovered.save_position("C:/x.mkv", "x", 15_000, 600_000)  # and it works
    recovered.close()


def test_newer_schema_is_left_untouched(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    LibraryDatabase(path).close()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    before = path.read_bytes()
    db = LibraryDatabase(path)
    assert db.read_only_reason is not None and "newer version" in db.read_only_reason
    db.save_position("C:/a.mkv", "a", 20_000, 600_000)  # goes to the in-memory stand-in
    db.close()
    assert path.read_bytes() == before


# --------------------------------------------------------------- folders
def test_folder_rules(db: LibraryDatabase, tmp_path: Path) -> None:
    (tmp_path / "movies" / "kids").mkdir(parents=True)
    movies = db.add_folder(str(tmp_path / "movies"))
    with pytest.raises(LibraryError, match="already in the library"):
        db.add_folder(str(tmp_path / "MOVIES"))  # same folder, other case (Windows)
    with pytest.raises(LibraryError, match="is inside"):
        db.add_folder(str(tmp_path / "movies" / "kids"))
    with pytest.raises(LibraryError, match="not a folder"):
        db.add_folder(str(tmp_path / "missing"))
    root = db.add_folder(str(tmp_path))  # a parent replaces its children
    assert [f.id for f in db.folders()] == [root.id]
    assert movies.id not in [f.id for f in db.folders()]


def test_parent_folder_keeps_existing_entries(db: LibraryDatabase, tmp_path: Path) -> None:
    touch(tmp_path / "movies" / "a.mp4")
    db.add_folder(str(tmp_path / "movies"))
    scan(db, tmp_path / "movies")
    root = db.add_folder(str(tmp_path))
    entries = db.media()
    assert len(entries) == 1 and entries[0].folder_id == root.id


def test_removing_a_folder_keeps_files_and_history(db: LibraryDatabase, tmp_path: Path) -> None:
    clip = touch(tmp_path / "a.mp4")
    folder = db.add_folder(str(tmp_path))
    scan(db, tmp_path)
    db.save_position(str(clip), "a.mp4", 30_000, 600_000)
    db.remove_folder(folder.id)
    assert db.media() == []
    assert clip.exists()
    assert db.history_for(str(clip)) is not None


# --------------------------------------------------------------- scanning
def test_scan_finds_media_only_and_skips_hidden(db: LibraryDatabase, tmp_path: Path) -> None:
    touch(tmp_path / "a.mp4")
    touch(tmp_path / "sub" / "deeper" / "b.MKV", CLIP + b"b")
    touch(tmp_path / "music" / "c.flac", CLIP + b"c")
    touch(tmp_path / ".hidden" / "d.mp4", CLIP + b"d")
    touch(tmp_path / ".e.mp4", CLIP + b"e")
    touch(tmp_path / "notes.txt")
    touch(tmp_path / "a.srt")
    db.add_folder(str(tmp_path))
    summary = scan(db, tmp_path)
    assert summary.files == 3 and not summary.cancelled
    assert sorted(m.name for m in db.media()) == ["a.mp4", "b.MKV", "c.flac"]


def test_rescan_marks_missing_and_reprobes_changed(db: LibraryDatabase, tmp_path: Path) -> None:
    a, b = touch(tmp_path / "a.mp4"), touch(tmp_path / "b.mp4", CLIP + b"b")
    db.add_folder(str(tmp_path))
    scan(db, tmp_path)
    for media_id, _ in db.media_to_probe():
        db.set_probe_result(media_id, None)
    assert db.counts() == (2, 0, 0)
    a.unlink()
    b.write_bytes(CLIP + b"changed")
    os.utime(b, (time.time() + 5, time.time() + 5))
    summary = scan(db, tmp_path)
    assert summary.missing == 1
    by_name = {m.name: m for m in db.media()}
    assert not by_name["a.mp4"].available  # kept, shown as not found
    assert by_name["b.mp4"].available and not by_name["b.mp4"].probed  # changed: details read again
    assert db.counts() == (2, 1, 1)
    touch(tmp_path / "a.mp4")  # it comes back
    scan(db, tmp_path)
    assert all(m.available for m in db.media())
    assert db.remove_unavailable() == 0


def test_cancelled_scan_marks_nothing_missing(db: LibraryDatabase, tmp_path: Path) -> None:
    touch(tmp_path / "a.mp4")
    db.add_folder(str(tmp_path))
    scan(db, tmp_path)
    cancel = threading.Event()
    cancel.set()
    summary = scan(db, tmp_path, cancel)
    assert summary.cancelled and summary.missing == 0
    assert db.media()[0].available


def test_unreachable_folder_marks_its_media_unavailable(db: LibraryDatabase, tmp_path: Path) -> None:
    folder_path = tmp_path / "usb"
    touch(folder_path / "a.mp4")
    db.add_folder(str(folder_path))
    scan(db, folder_path)
    folder_path.rename(tmp_path / "unplugged")
    folder = db.folders()[0]
    summary = scan_folder(db, folder, threading.Event())
    assert not summary.available
    assert not db.folders()[0].available and not db.media()[0].available
    (tmp_path / "unplugged").rename(folder_path)
    scan_folder(db, db.folders()[0], threading.Event())
    assert db.folders()[0].available and db.media()[0].available


def test_duplicates_are_detected_and_both_kept(db: LibraryDatabase, tmp_path: Path) -> None:
    touch(tmp_path / "one" / "film.mp4")
    touch(tmp_path / "two" / "film copy.mp4")
    touch(tmp_path / "two" / "other.mp4", CLIP + b"different")
    db.add_folder(str(tmp_path))
    scan(db, tmp_path)
    by_name = {m.name: m for m in db.media()}
    assert by_name["film.mp4"].duplicates == 1 and by_name["film copy.mp4"].duplicates == 1
    assert by_name["other.mp4"].duplicates == 0
    assert db.duplicates_of(by_name["film.mp4"].id) == [str(tmp_path / "two" / "film copy.mp4")]


def test_same_file_under_two_spellings_is_one_entry(db: LibraryDatabase, tmp_path: Path) -> None:
    clip = touch(tmp_path / "Film.mp4")
    assert path_key(str(clip)) == path_key(str(clip).upper()) == path_key(str(clip).replace("\\", "/"))
    db.save_position(str(clip), "Film.mp4", 20_000, 600_000)
    db.save_position(str(clip).upper(), "Film.mp4", 30_000, 600_000)
    assert db.history_count() == 1


def test_search_and_sort(db: LibraryDatabase, tmp_path: Path) -> None:
    touch(tmp_path / "Holiday 2024.mp4", CLIP * 3)
    touch(tmp_path / "50% off_promo.mp4", CLIP * 2)
    touch(tmp_path / "concert" / "song.flac", CLIP + b"x")
    db.add_folder(str(tmp_path))
    scan(db, tmp_path)
    assert [m.name for m in db.media("holiday")] == ["Holiday 2024.mp4"]
    assert [m.name for m in db.media("50%")] == ["50% off_promo.mp4"]  # % is literal
    assert [m.name for m in db.media("f_p")] == ["50% off_promo.mp4"]  # _ is literal
    assert [m.name for m in db.media("concert")] == ["song.flac"]  # folder names match
    assert db.media(sort=SortOrder.SIZE)[0].name == "Holiday 2024.mp4"
    db.save_position(str(tmp_path / "concert" / "song.flac"), "song.flac", 12_000, 600_000)
    assert db.media(sort=SortOrder.RECENTLY_PLAYED)[0].name == "song.flac"


# ---------------------------------------------------------------- history
@pytest.mark.parametrize(
    ("position", "duration", "finished", "expected"),
    [
        (5_000, 600_000, False, 0),  # less than RESUME_MIN_MS watched
        (RESUME_MIN_MS, 600_000, False, RESUME_MIN_MS),
        (300_000, 600_000, False, 300_000),
        (590_000, 600_000, False, 0),  # last 15 s: finished
        (3_500_000, 3_600_000, False, 0),  # last 3 % of an hour
        (3_400_000, 3_600_000, False, 3_400_000),
        (300_000, 600_000, True, 0),
        (300_000, None, False, 300_000),  # unknown duration: resume
    ],
)
def test_resume_rules(position: int, duration: int | None, finished: bool, expected: int) -> None:
    assert resume_position(position, duration, finished) == expected


def test_is_finished_without_duration() -> None:
    assert not is_finished(10_000, None)


def test_history_record_save_continue_clear(db: LibraryDatabase) -> None:
    db.record_play("mock://a", "a", 600_000)
    db.save_position("mock://a", "a", 120_000, 600_000)
    db.record_play("mock://b", "b", 600_000)
    db.save_position("mock://b", "b", 595_000, 600_000)  # finished
    db.record_play("mock://c", "c", 600_000)  # just started
    entry = db.history_for("mock://a")
    assert entry is not None and entry.play_count == 1 and entry.position_ms == 120_000
    assert abs(entry.progress - 0.2) < 1e-9
    assert [e.path for e in db.continue_watching()] == ["mock://a"]
    assert [e.path for e in db.recent()] == ["mock://c", "mock://b", "mock://a"]
    db.record_play("mock://a", "a", None)
    entry = db.history_for("mock://a")
    assert entry is not None and entry.play_count == 2 and entry.duration_ms == 600_000
    db.mark_finished("mock://a")
    assert db.continue_watching() == []
    db.remove_history("mock://c")
    assert db.history_count() == 2
    db.clear_history()
    assert db.recent() == []


def test_continue_watching_hides_missing_files(db: LibraryDatabase, tmp_path: Path) -> None:
    clip = touch(tmp_path / "a.mp4")
    db.save_position(str(clip), "a.mp4", 60_000, 600_000)
    assert len(db.continue_watching()) == 1
    clip.unlink()
    assert db.continue_watching() == []
    assert not db.recent()[0].available  # still listed, marked


# --------------------------------------------------------------- playlists
def test_playlists(db: LibraryDatabase, tmp_path: Path) -> None:
    a, b, c = (touch(tmp_path / f"{n}.mp4", CLIP + n.encode()) for n in "abc")
    with pytest.raises(LibraryError):
        db.create_playlist("   ")
    playlist = db.create_playlist("  Road   trip ")
    assert playlist.name == "Road trip"
    db.add_to_playlist(playlist.id, [str(a), str(b), str(c)])
    items = db.playlist_items(playlist.id)
    assert [i.title for i in items] == ["a.mp4", "b.mp4", "c.mp4"]
    db.move_playlist_item(items[2].id, -2)
    assert [i.title for i in db.playlist_items(playlist.id)] == ["c.mp4", "a.mp4", "b.mp4"]
    db.move_playlist_item(items[2].id, -5)  # clamped
    db.remove_playlist_item(items[0].id)
    assert [i.title for i in db.playlist_items(playlist.id)] == ["c.mp4", "b.mp4"]
    b.unlink()
    assert [i.available for i in db.playlist_items(playlist.id)] == [True, False]
    db.rename_playlist(playlist.id, "Trip")
    assert db.playlists()[0].name == "Trip" and db.playlists()[0].item_count == 2
    db.delete_playlist(playlist.id)
    assert db.playlists() == [] and db._query("SELECT COUNT(*) FROM playlist_items")[0][0] == 0


def test_playlist_name_is_limited(db: LibraryDatabase) -> None:
    assert len(db.create_playlist("x" * 500).name) == dbmod.MAX_PLAYLIST_NAME


# ------------------------------------------------------------ bookmarks (M8)
def test_bookmarks_are_kept_per_file_in_time_order(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.db")
    db.add_bookmark("C:/Films/a.mkv", 90_000, "  The   chase ")
    db.add_bookmark("C:/Films/a.mkv", 30_000, "")
    db.add_bookmark("C:/Films/b.mkv", 5_000, "other")
    marks = db.bookmarks_for("c:/films/A.mkv")  # same file, different spelling (path_key)
    assert [(b.position_ms, b.label) for b in marks] == [(30_000, ""), (90_000, "The chase")]
    db.rename_bookmark(marks[0].id, "Start " * 40)
    assert db.bookmarks_for("C:/Films/a.mkv")[0].label == ("Start " * 40)[:120].strip()
    db.delete_bookmark(marks[1].id)
    assert len(db.bookmarks_for("C:/Films/a.mkv")) == 1
    db.clear_bookmarks("C:/Films/a.mkv")
    assert db.bookmarks_for("C:/Films/a.mkv") == [] and len(db.bookmarks_for("C:/Films/b.mkv")) == 1
    db.close()


def test_bookmark_limit_and_stream_addresses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dbmod, "MAX_BOOKMARKS_PER_FILE", 3)
    db = LibraryDatabase(tmp_path / "library.db")
    url = "https://example.com/show.mp4?token=1"
    for ms in (1, 2, 3):
        db.add_bookmark(url, ms * 1000, "")
    with pytest.raises(LibraryError):
        db.add_bookmark(url, 4000, "")
    assert db.add_bookmark("C:/other.mkv", -5, "").position_ms == 0  # clamped
    db.close()


def test_clearing_history_keeps_bookmarks(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.db")
    db.record_play("C:/a.mkv", "a.mkv", 600_000)
    db.add_bookmark("C:/a.mkv", 12_000, "note")
    db.clear_history()
    assert db.history_count() == 0 and len(db.bookmarks_for("C:/a.mkv")) == 1
    db.close()
