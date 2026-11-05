"""Grouping songs into albums and artists. Plain data, no database or UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from babarify_frame.library.models import MediaEntry


class GroupKind(StrEnum):
    ALBUM = "album"
    ARTIST = "artist"


class SongSort(StrEnum):
    TITLE = "title"
    ARTIST = "artist"
    ALBUM = "album"
    RECENTLY_ADDED = "recently_added"
    LONGEST = "longest"
    OLDEST_ADDED = "oldest_added"
    MOST_PLAYED = "most_played"
    YEAR = "year"
    FOLDER = "folder"


SONG_SORT_LABELS = {
    SongSort.TITLE: "Title",
    SongSort.ARTIST: "Artist",
    SongSort.ALBUM: "Album",
    SongSort.FOLDER: "Folder",
    SongSort.RECENTLY_ADDED: "Newest first",
    SongSort.OLDEST_ADDED: "Oldest first",
    SongSort.MOST_PLAYED: "Most played",
    SongSort.YEAR: "Year",
    SongSort.LONGEST: "Longest first",
}
UNKNOWN_ALBUM = "Unknown album"
UNKNOWN_ARTIST = "Unknown artist"
VARIOUS_ARTISTS = "Various artists"


@dataclass(frozen=True)
class SongGroup:
    kind: GroupKind
    key: str
    title: str  # what to show; files with no tag are gathered under "Unknown ..."
    artist: str  # for an album: its artist, or "Various artists"
    songs: tuple[MediaEntry, ...]

    @property
    def picture(self) -> MediaEntry | None:
        """The first song that has a picture stands for the whole group."""
        return next((song for song in self.songs if song.thumbnail), None)


def _album_key(song: MediaEntry) -> str:
    """An album's title and folder. Artists can differ on one album, as on a compilation or with a guest,
    while two albums with one title, like "Greatest Hits", are normally kept in different folders."""
    if not song.album:
        return ""
    return f"{song.album.casefold()}|{os.path.dirname(song.path).casefold()}"


def group_songs(songs: list[MediaEntry], kind: GroupKind) -> list[SongGroup]:
    """Albums or artists, sorted by name, with the unknown group last."""
    gathered: dict[str, list[MediaEntry]] = {}
    for song in songs:
        key = _album_key(song) if kind is GroupKind.ALBUM else (song.artist or "").casefold()
        gathered.setdefault(key, []).append(song)
    groups = []
    for key, members in gathered.items():
        first = members[0]
        if kind is GroupKind.ALBUM:
            title = first.album or UNKNOWN_ALBUM
            artists = {(song.artist or "").casefold() for song in members}
            artist = (first.artist or UNKNOWN_ARTIST) if len(artists) == 1 else VARIOUS_ARTISTS
        else:
            title = first.artist or UNKNOWN_ARTIST
            artist = ""
        ordered = tuple(sorted(members, key=lambda s: s.display_title.casefold()))
        groups.append(SongGroup(kind, key, title, artist, ordered))
    return sorted(groups, key=lambda g: (not g.key, g.title.casefold()))
