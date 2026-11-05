"""Backing up settings and lists, and restoring them."""

from __future__ import annotations

from pathlib import Path

import pytest

from babarify_frame.configuration.preferences import Preferences
from babarify_frame.library import backup
from babarify_frame.library.database import LibraryDatabase


def test_a_backup_brings_lists_and_settings_back(tmp_path: Path) -> None:
    source = LibraryDatabase(tmp_path / "source.db")
    playlist = source.create_playlist("Road trip")
    source.add_to_playlist(playlist.id, ["C:/music/a.mp3", "C:/music/b.mp3"])
    source.set_favourite("C:/music/a.mp3", "A", True)
    source.hide_media(["C:/music/voice.m4a"])
    file = tmp_path / "backup.json"
    backup.write_backup(file, backup.build_backup(Preferences(colour_theme="light"), source))

    target = LibraryDatabase(tmp_path / "target.db")
    data = backup.read_backup(file)
    assert Preferences.from_dict(data["preferences"]).colour_theme == "light"
    assert "history" not in data, "what was played stays out of the file"
    restored = backup.restore_lists(data, target)
    assert (restored.playlists, restored.favourites, restored.hidden) == (1, 1, 1)
    copy = target.playlists()[0]
    assert copy.name == "Road trip"
    assert [item.path for item in target.playlist_items(copy.id)] == ["C:/music/a.mp3", "C:/music/b.mp3"]
    assert target.is_favourite("C:/music/a.mp3")
    assert target.hidden_media() == ["C:/music/voice.m4a"]


def test_restoring_adds_without_removing_or_doubling(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.db")
    playlist = db.create_playlist("Mine")
    db.add_to_playlist(playlist.id, ["C:/music/mine.mp3"])
    data = {
        "format": backup.FORMAT,
        "version": backup.VERSION,
        "playlists": [
            {"name": "Mine", "paths": ["C:/music/mine.mp3", "C:/music/new.mp3"]},
            {"name": 5},
            "junk",
        ],
        "favourites": [{"path": "C:/music/new.mp3", "title": "New"}, {"nothing": 1}],
    }
    first = backup.restore_lists(data, db)
    assert (first.playlists, first.favourites) == (0, 1)
    assert [i.path for i in db.playlist_items(playlist.id)] == ["C:/music/mine.mp3", "C:/music/new.mp3"]
    second = backup.restore_lists(data, db)
    assert (second.playlists, second.favourites) == (0, 0)
    assert len(db.playlist_items(playlist.id)) == 2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "couldn't be read"),
        ("[]", "isn't a Babarify backup"),
        ('{"format": "other", "version": 1}', "isn't a Babarify backup"),
        ('{"format": "babarify-backup", "version": 99}', "newer version"),
    ],
)
def test_a_file_that_is_not_a_backup_is_refused(tmp_path: Path, text: str, message: str) -> None:
    file = tmp_path / "file.json"
    file.write_text(text, encoding="utf-8")
    with pytest.raises(backup.BackupError, match=message):
        backup.read_backup(file)
