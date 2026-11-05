"""Repeat, shuffle, the animations' movement, and reading pictures out of music files."""

from __future__ import annotations

import base64
import random
import struct
from pathlib import Path

import pytest

from babarify_frame.configuration.preferences import Preferences
from babarify_frame.core import music
from babarify_frame.core.cover_art import read_embedded_picture
from babarify_frame.core.music import RepeatMode, VisualStyle, index_after_end, shuffled

PICTURE = b"\xff\xd8\xff\xe0 not a real jpeg, the reader doesn't decode it"


def test_repeat_cycles_through_its_modes() -> None:
    assert RepeatMode.OFF.next() is RepeatMode.ONE
    assert RepeatMode.ONE.next() is RepeatMode.ALL
    assert RepeatMode.ALL.next() is RepeatMode.OFF


@pytest.mark.parametrize(
    ("index", "length", "mode", "expected"),
    [
        (0, 3, RepeatMode.OFF, 1),
        (2, 3, RepeatMode.OFF, None),
        (1, 3, RepeatMode.ONE, 1),
        (2, 3, RepeatMode.ALL, 0),
        (0, 3, RepeatMode.ALL, 1),
        (0, 0, RepeatMode.ALL, None),
    ],
)
def test_what_plays_after_a_file_ends(
    index: int, length: int, mode: RepeatMode, expected: int | None
) -> None:
    assert index_after_end(index, length, mode) == expected


def test_shuffling_keeps_the_current_file_first_and_every_file() -> None:
    items = [f"song{i}" for i in range(20)]
    mixed = shuffled(items, 7, random.Random(1))
    assert mixed[0] == "song7"
    assert sorted(mixed) == sorted(items)
    assert mixed != items


def test_bars_stay_in_range_and_really_move() -> None:
    for bar in range(16):
        levels = [music.level(bar, t) for t in range(0, 5000, 40)]
        assert all(music.REST_LEVEL <= value <= 1 for value in levels)
        assert max(levels) - min(levels) > 0.3


def test_bars_make_a_shape_and_peaks_fall_slowly() -> None:
    assert music.envelope(9, 19) == pytest.approx(1.0)
    assert music.envelope(0, 19) < music.envelope(5, 19)
    assert music.peak(0.2, 0.9) == 0.9
    assert 0.8 < music.peak(0.9, 0.2) < 0.9


def test_automatic_style_visits_every_style_in_turn() -> None:
    styles = music.STYLE_CYCLE
    assert VisualStyle.AUTO not in styles
    assert [music.auto_style(i * music.AUTO_SWITCH_MS) for i in range(len(styles))] == list(styles)
    assert music.auto_style(len(styles) * music.AUTO_SWITCH_MS) == styles[0]
    assert music.auto_style(-5) == styles[0]


def test_preferences_refuse_unknown_music_settings() -> None:
    prefs = Preferences.from_dict({"repeat_mode": "sideways", "visual_style": "fireworks"})
    assert prefs.repeat_mode == "off"
    assert prefs.visual_style == "auto"
    good = Preferences.from_dict({"repeat_mode": "all", "visual_style": "circle"})
    assert (good.repeat_mode, good.visual_style) == ("all", "circle")


# ------------------------------------------------------------- embedded pictures
def synchsafe(value: int) -> bytes:
    return bytes((value >> shift) & 0x7F for shift in (21, 14, 7, 0))


def id3(frames: bytes, version: int = 3) -> bytes:
    return b"ID3" + bytes([version, 0, 0]) + synchsafe(len(frames)) + frames + b"\xff\xfb audio"


def apic(
    picture: bytes, kind: int = 3, version: int = 3, encoding: int = 0, description: bytes = b"\0"
) -> bytes:
    body = bytes([encoding]) + b"image/jpeg\0" + bytes([kind]) + description + picture
    size = synchsafe(len(body)) if version == 4 else struct.pack(">I", len(body))
    return b"APIC" + size + b"\0\0" + body


def flac_picture(picture: bytes, kind: int = 3) -> bytes:
    return (
        struct.pack(">I", kind)
        + struct.pack(">I", 10)
        + b"image/jpeg"
        + struct.pack(">I", 0)
        + bytes(16)
        + struct.pack(">I", len(picture))
        + picture
    )


def atom(name: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 8) + name + body


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("version", [3, 4])
def test_id3_picture(tmp_path: Path, version: int) -> None:
    other = b"TIT2" + (synchsafe(5) if version == 4 else struct.pack(">I", 5)) + b"\0\0\0Song"
    data = id3(other + apic(PICTURE, version=version), version)
    assert read_embedded_picture(write(tmp_path, "a.mp3", data)) == PICTURE


def test_id3_description_in_utf16_is_stepped_over(tmp_path: Path) -> None:
    data = id3(apic(PICTURE, encoding=1, description="Cover".encode("utf-16") + b"\0\0"))
    assert read_embedded_picture(write(tmp_path, "a.mp3", data)) == PICTURE


def test_id3_prefers_the_front_cover(tmp_path: Path) -> None:
    data = id3(apic(b"back cover", kind=4) + apic(PICTURE, kind=3))
    assert read_embedded_picture(write(tmp_path, "a.mp3", data)) == PICTURE


def test_id3_with_only_another_picture_uses_it(tmp_path: Path) -> None:
    assert read_embedded_picture(write(tmp_path, "a.mp3", id3(apic(b"band photo", kind=8)))) == b"band photo"


def test_flac_picture(tmp_path: Path) -> None:
    block = flac_picture(PICTURE)
    info = bytes([0]) + (34).to_bytes(3, "big") + bytes(34)
    data = b"fLaC" + info + bytes([0x80 | 6]) + len(block).to_bytes(3, "big") + block
    assert read_embedded_picture(write(tmp_path, "a.flac", data)) == PICTURE


def test_m4a_picture(tmp_path: Path) -> None:
    covr = atom(b"covr", atom(b"data", bytes(8) + PICTURE))
    moov = atom(b"moov", atom(b"udta", atom(b"meta", bytes(4) + atom(b"ilst", covr))))
    data = atom(b"ftyp", b"M4A \0\0\0\0") + atom(b"mdat", b"audio") + moov
    assert read_embedded_picture(write(tmp_path, "a.m4a", data)) == PICTURE


def ogg_page(body: bytes) -> bytes:
    segments = [255] * (len(body) // 255) + [len(body) % 255]
    return b"OggS" + bytes(22) + bytes([len(segments)]) + bytes(segments) + body


@pytest.mark.parametrize(("marker", "name"), [(b"\x03vorbis", "a.ogg"), (b"OpusTags", "a.opus")])
def test_ogg_picture(tmp_path: Path, marker: bytes, name: str) -> None:
    comment = b"METADATA_BLOCK_PICTURE=" + base64.b64encode(flac_picture(PICTURE))
    plain = b"TITLE=Song"
    body = marker + struct.pack("<I", 0) + struct.pack("<I", 2)
    for item in (plain, comment):
        body += struct.pack("<I", len(item)) + item
    data = ogg_page(b"\x01vorbis header") + ogg_page(body)
    assert read_embedded_picture(write(tmp_path, name, data)) == PICTURE


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"ID3",
        id3(b""),
        id3(b"APIC" + struct.pack(">I", 1_000_000) + b"\0\0short"),
        b"ID3\x03\0\0" + synchsafe(10_000_000) + b"APIC",
        b"fLaC" + bytes([0x86]) + (500).to_bytes(3, "big") + b"short",
        b"fLaC" + bytes([0x86, 0xFF, 0xFF, 0xFF]),
        atom(b"ftyp", b"M4A ") + struct.pack(">I", 3) + b"moov",
        atom(b"ftyp", b"M4A ") + struct.pack(">I", 1000) + b"moov" + b"short",
        ogg_page(b"OpusTags" + struct.pack("<I", 4_000_000)),
        ogg_page(b"OpusTags" + struct.pack("<I", 0) + struct.pack("<I", 99)),
        b"just some bytes that are not a music file",
    ],
)
def test_damaged_files_simply_have_no_picture(tmp_path: Path, data: bytes) -> None:
    assert read_embedded_picture(write(tmp_path, "bad.mp3", data)) is None


def test_a_missing_file_has_no_picture(tmp_path: Path) -> None:
    assert read_embedded_picture(tmp_path / "gone.mp3") is None
