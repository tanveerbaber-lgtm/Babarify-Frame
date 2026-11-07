"""What has been listened to, worked out on this PC from the play counts in the library."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from babarify_frame.library.models import MediaEntry

TOP = 5


@dataclass(frozen=True)
class Recap:
    plays: int
    listened_ms: int
    songs_played: int
    top_songs: list[tuple[MediaEntry, int]]
    top_artists: list[tuple[str, int]]
    top_albums: list[tuple[str, int]]
    never_played: list[MediaEntry]


def build(songs: list[MediaEntry], counts: dict[str, int]) -> Recap:
    """``counts`` gives how many times each song has been played, by its path."""
    played = sorted(
        ((song, counts[song.path]) for song in songs if counts.get(song.path, 0) > 0),
        key=lambda pair: (-pair[1], pair[0].display_title.casefold()),
    )
    artists: Counter[str] = Counter()
    albums: Counter[str] = Counter()
    for song, times in played:
        if song.artist:
            artists[song.artist] += times
        if song.album:
            albums[song.album] += times
    return Recap(
        plays=sum(times for _, times in played),
        listened_ms=sum((song.duration_ms or 0) * times for song, times in played),
        songs_played=len(played),
        top_songs=played[:TOP],
        top_artists=_top(artists),
        top_albums=_top(albums),
        never_played=[song for song in songs if counts.get(song.path, 0) == 0][:TOP],
    )


def _top(counter: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda pair: (-pair[1], pair[0].casefold()))[:TOP]


def counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def listening_time(milliseconds: int) -> str:
    minutes = milliseconds // 60_000
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if hours else f"{rest} min"
