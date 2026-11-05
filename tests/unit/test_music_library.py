"""Songs' tags in the library, albums and artists, favourites and the automatic lists."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace
from pathlib import Path

from babarify_frame.library.database import (
    AUTOMATIC_LIST_SIZE,
    SCHEMA_VERSION,
    LibraryDatabase,
    ProbeRecord,
    ScanRecord,
)
from babarify_frame.library.models import MediaEntry, path_key
from babarify_frame.library.music import (
    UNKNOWN_ALBUM,
    UNKNOWN_ARTIST,
    VARIOUS_ARTISTS,
    GroupKind,
    SongSort,
    group_songs,
)


def add(db: LibraryDatabase, folder_id: int, name: str, **tags: object) -> str:
    path = f"C:/music/{name}"
    db.upsert_media([ScanRecord(path, folder_id, 100, 1.0, None)], time.time())
    entry = db.media_by_path(path)
    assert entry is not None
    video = tags.pop("video_codec", None)
    audio = tags.pop("audio_codec", "mp3")
    db.set_probe_result(
        entry.id,
        ProbeRecord(
            tags.pop("duration_ms", 1000),  # type: ignore[arg-type]
            None,
            None,
            video,  # type: ignore[arg-type]
            audio,  # type: ignore[arg-type]
            None,
            tags.pop("title", None),  # type: ignore[arg-type]
            tags.pop("artist", None),  # type: ignore[arg-type]
            tags.pop("album", None),  # type: ignore[arg-type]
        ),
    )
    return path


def library(tmp_path: Path) -> tuple[LibraryDatabase, int]:
    db = LibraryDatabase(None)
    music = tmp_path / "music"
    music.mkdir(exist_ok=True)
    return db, db.add_folder(str(music)).id


def song(
    name: str, artist: str | None = None, album: str | None = None, thumbnail: str | None = None
) -> MediaEntry:
    return MediaEntry(
        id=abs(hash(name)) % 100000,
        path=f"C:/{name}",
        name=f"{name}.mp3",
        folder_id=1,
        size=1,
        mtime=1.0,
        added_at=1.0,
        title=name,
        artist=artist,
        album=album,
        thumbnail=thumbnail,
    )


def test_songs_leave_out_video_and_use_their_tags(tmp_path: Path) -> None:
    db, folder = library(tmp_path)
    add(db, folder, "01.mp3", title="Golden Sky", artist="Lucas", album="Horizons")
    add(db, folder, "film.mkv", video_codec="h264", audio_codec="aac")
    add(db, folder, "clip.mp4", audio_codec="aac")  # sound only, whatever the name says
    add(db, folder, "cover.m4a", video_codec="mjpeg", audio_codec="aac")  # its picture looks like video
    names = sorted(entry.name for entry in db.songs())
    assert names == ["01.mp3", "clip.mp4", "cover.m4a"]
    tagged = next(entry for entry in db.songs() if entry.name == "01.mp3")
    assert (tagged.title, tagged.artist, tagged.album) == ("Golden Sky", "Lucas", "Horizons")
    assert tagged.display_title == "Golden Sky"
    plain = next(entry for entry in db.songs() if entry.name == "clip.mp4")
    assert plain.display_title == "clip"


def test_songs_search_every_word_across_tags(tmp_path: Path) -> None:
    db, folder = library(tmp_path)
    add(db, folder, "1.mp3", title="Golden Sky", artist="Lucas", album="Horizons")
    add(db, folder, "2.mp3", title="Silver Sky", artist="Mira", album="Horizons")
    assert [e.title for e in db.songs("lucas")] == ["Golden Sky"]
    assert len(db.songs("horizons sky")) == 2
    assert [e.title for e in db.songs("sky mira")] == ["Silver Sky"]
    assert db.songs("nothing") == []
    assert db.songs("100%") == []  # A search can't be read as a pattern.


def test_songs_sort(tmp_path: Path) -> None:
    db, folder = library(tmp_path)
    add(db, folder, "a.mp3", title="Beta", artist="Zed", album="One", duration_ms=5)
    time.sleep(0.01)
    add(db, folder, "b.mp3", title="alpha", artist="Abba", album="Two", duration_ms=9)
    time.sleep(0.01)
    add(db, folder, "c.mp3", title="Gamma", duration_ms=1)
    titles = lambda order: [e.title for e in db.songs(sort=order)]  # noqa: E731
    assert titles(SongSort.TITLE) == ["alpha", "Beta", "Gamma"]
    assert titles(SongSort.ARTIST) == ["alpha", "Beta", "Gamma"]
    assert titles(SongSort.ALBUM) == ["Beta", "alpha", "Gamma"]
    assert titles(SongSort.RECENTLY_ADDED) == ["Gamma", "alpha", "Beta"]
    assert titles(SongSort.LONGEST) == ["alpha", "Beta", "Gamma"]


def test_albums_group_with_unknowns_last() -> None:
    songs = [
        song("b", "Zed", "Two"),
        song("a", "zed", "two"),
        song("c", "Mira", "One"),
        song("d"),
    ]
    albums = group_songs(songs, GroupKind.ALBUM)
    assert [a.title for a in albums] == ["One", "Two", UNKNOWN_ALBUM]
    assert [s.title for s in albums[1].songs] == ["a", "b"], "different capitals are one album"
    assert albums[0].artist == "Mira"


def test_an_album_with_several_artists_stays_one_album() -> None:
    albums = group_songs([song("a", "Zed", "Mix"), song("b", "Mira", "Mix")], GroupKind.ALBUM)
    assert len(albums) == 1
    assert albums[0].artist == VARIOUS_ARTISTS


def test_one_album_title_in_two_folders_is_two_albums() -> None:
    first = replace(song("a", "Zed", "Greatest Hits"), path="C:/zed/a.mp3")
    second = replace(song("b", "Mira", "Greatest Hits"), path="C:/mira/b.mp3")
    assert len(group_songs([first, second], GroupKind.ALBUM)) == 2


def test_artists_group_with_unknowns_last() -> None:
    artists = group_songs([song("a", "Zed"), song("b", "ZED"), song("c")], GroupKind.ARTIST)
    assert [a.title for a in artists] == ["Zed", UNKNOWN_ARTIST]
    assert len(artists[0].songs) == 2


def test_a_group_takes_the_first_picture_it_has() -> None:
    album = group_songs([song("a", "Z", "One"), song("b", "Z", "One", thumbnail="x.jpg")], GroupKind.ALBUM)[0]
    assert album.picture is not None and album.picture.thumbnail == "x.jpg"


def test_favourites_add_remove_and_repeat(tmp_path: Path) -> None:
    db, _folder = library(tmp_path)
    path = str(tmp_path / "a.mp3")
    Path(path).write_bytes(b"x")
    assert not db.is_favourite(path)
    db.set_favourite(path, "A song", True)
    db.set_favourite(path, "A song", True)
    assert db.is_favourite(path)
    assert [(f.title, f.available) for f in db.favourites()] == [("A song", True)]
    Path(path).unlink()
    assert not db.favourites()[0].available, "a moved file is marked, not lost"
    db.set_favourite(path, "A song", False)
    assert db.favourites() == []


def test_favourites_survive_clearing_history(tmp_path: Path) -> None:
    db, _folder = library(tmp_path)
    db.set_favourite("C:/a.mp3", "A", True)
    db.record_play("C:/a.mp3", "A", 1000)
    assert db.recently_played_songs()
    db.clear_history()
    assert db.recently_played_songs() == [] and db.most_played_songs() == []
    assert db.is_favourite("C:/a.mp3")


def test_played_lists_hold_only_music_in_the_right_order(tmp_path: Path) -> None:
    db, _folder = library(tmp_path)
    db.record_play("C:/film.mkv", "A film", 1000)
    db.record_play("C:/one.mp3", "One", 1000)
    time.sleep(0.01)
    for _ in range(3):
        db.record_play("C:/two.mp3", "Two", 1000)
    time.sleep(0.01)
    db.record_play("C:/three.flac", "Three", 1000)
    assert [i.title for i in db.recently_played_songs()] == ["Three", "Two", "One"]
    assert db.most_played_songs()[0].title == "Two"


def test_automatic_lists_are_limited(tmp_path: Path) -> None:
    db, folder = library(tmp_path)
    for index in range(AUTOMATIC_LIST_SIZE + 5):
        add(db, folder, f"{index}.mp3", title=f"Song {index}")
    assert len(db.recently_added_songs()) == AUTOMATIC_LIST_SIZE


def test_existing_library_is_kept_and_only_its_music_read_again(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    conn = sqlite3.connect(path, isolation_level=None)
    LibraryDatabase._migrate(conn, target=4)
    conn.execute("INSERT INTO folders(id, path, path_key, added_at) VALUES (1, 'C:/m', 'c:/m', 1)")
    for number, (name, video, audio) in enumerate(
        [
            ("song.mp3", None, "mp3"),
            ("film.mkv", "h264", "aac"),
            ("speech.mp4", None, "aac"),
            ("art.m4a", "mjpeg", "aac"),
        ]
    ):
        conn.execute(
            """INSERT INTO media(id, folder_id, path, path_key, name, size, mtime, added_at, scanned_at,
               probed, video_codec, audio_codec, duration_ms)
               VALUES (?, 1, ?, ?, ?, 1, 1, 1, 1, 1, ?, ?, 5000)""",
            (number, f"C:/m/{name}", path_key(f"C:/m/{name}"), name, video, audio),
        )
    conn.execute(
        "INSERT INTO history(path_key, path, title, play_count, last_played_at) "
        "VALUES ('k', 'C:/m/song.mp3', 'S', 7, 1)"
    )
    conn.close()
    db = LibraryDatabase(path)
    assert db.schema_version == SCHEMA_VERSION
    assert db.recovered is None
    assert sorted(name.rsplit("/", 1)[-1] for _id, name in db.media_to_probe()) == [
        "art.m4a",
        "song.mp3",
        "speech.mp4",
    ]
    film = db.media_by_path("C:/m/film.mkv")
    assert film is not None and film.probed and film.duration_ms == 5000, "videos aren't read again"
    assert db._query("SELECT play_count FROM history")[0][0] == 7
    assert db.favourites() == []
    db.close()
