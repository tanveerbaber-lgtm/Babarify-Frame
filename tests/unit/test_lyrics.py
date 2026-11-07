"""Reading lyrics and following them."""

from __future__ import annotations

from pathlib import Path

from babarify_frame.library import lyrics


def test_timed_lyrics_are_ordered_and_followed() -> None:
    lines = lyrics.parse("\ufeff[ar:Someone]\n[00:12.50]Second\n[00:05.00][00:30.00]First\n\n")
    assert [line.text for line in lines] == ["First", "Second", "First"]
    assert [line.time_ms for line in lines] == [5000, 12500, 30000]
    assert lyrics.current_line(lines, 4999) == -1
    assert lyrics.current_line(lines, 5000) == 0
    assert lyrics.current_line(lines, 29999) == 1
    assert lyrics.current_line(lines, 99000) == 2


def test_plain_lyrics_keep_their_order_and_have_nothing_to_follow() -> None:
    lines = lyrics.parse("\nOne\n\nTwo\n")
    assert [line.text for line in lines] == ["One", "", "Two"]
    assert lyrics.current_line(lines, 50000) == -1
    assert lyrics.parse("") == []


def test_saved_lyrics_come_before_a_file_beside_the_song(tmp_path: Path) -> None:
    store = tmp_path / "store"
    song = tmp_path / "song.mp3"
    assert lyrics.load(str(song), store) is None
    (tmp_path / "song.lrc").write_text("[00:01.00]Beside", encoding="utf-8")
    assert lyrics.load(str(song), store) == "[00:01.00]Beside"
    lyrics.save(str(song), "Typed", store)
    assert lyrics.load(str(song), store) == "Typed"
