"""A file holding settings and lists, to keep safe or to move to another PC.

Playlists, favourites and hidden files are in it. Playback history and positions are not, so the file says
less about what was watched. Restoring adds to the lists that are there; it never removes anything from them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from babarify_frame.configuration.preferences import Preferences
from babarify_frame.library.database import LibraryDatabase

FORMAT = "babarify-backup"
VERSION = 1


class BackupError(Exception):
    """The file can't be used as a backup. The message is for the person using the app."""


@dataclass(frozen=True)
class Restored:
    playlists: int
    favourites: int
    hidden: int


def build_backup(prefs: Preferences, db: LibraryDatabase) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "version": VERSION,
        "preferences": prefs.to_dict(),
        "playlists": [
            {"name": playlist.name, "paths": [item.path for item in db.playlist_items(playlist.id)]}
            for playlist in db.playlists()
        ],
        "favourites": [{"path": item.path, "title": item.title} for item in db.favourites()],
        "hidden": db.hidden_media(),
    }


def write_backup(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_backup(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError("That file couldn't be read.") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("That file isn't a Babarify backup.")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise BackupError("That backup is from a newer version of the app.")
    return data


def restore_lists(data: dict[str, Any], db: LibraryDatabase) -> Restored:
    """Adds what the backup has. A playlist with the same name gains the files it doesn't have yet."""
    existing = {playlist.name: playlist.id for playlist in db.playlists()}
    playlists = 0
    for entry in _entries(data, "playlists"):
        name, paths = entry.get("name"), entry.get("paths")
        if not isinstance(name, str) or not name.strip() or not isinstance(paths, list):
            continue
        playlist_id = existing.get(name)
        if playlist_id is None:
            playlist_id = db.create_playlist(name).id
            playlists += 1
        have = {item.path for item in db.playlist_items(playlist_id)}
        db.add_to_playlist(playlist_id, [p for p in paths if isinstance(p, str) and p not in have])
    favourites = 0
    for entry in _entries(data, "favourites"):
        path, title = entry.get("path"), entry.get("title")
        if isinstance(path, str) and not db.is_favourite(path):
            db.set_favourite(path, title if isinstance(title, str) else "", True)
            favourites += 1
    hidden = data.get("hidden")
    paths = [p for p in hidden if isinstance(p, str)] if isinstance(hidden, list) else []
    db.hide_media(paths)
    return Restored(playlists, favourites, len(paths))


def _entries(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []
