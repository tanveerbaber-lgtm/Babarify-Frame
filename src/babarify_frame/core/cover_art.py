"""Finds the picture embedded in a music file, without decoding it.

libVLC only offers this by writing the picture into a cache folder, so the common tag formats are read
here: ID3v2 (MP3, and others that use it), FLAC, MP4/M4A and Ogg (Vorbis and Opus). Files are untrusted:
every length is checked against what's really there, and a damaged file simply has no picture.
"""

from __future__ import annotations

import base64
import binascii
import logging
import struct
from pathlib import Path

log = logging.getLogger(__name__)

MAX_PICTURE_BYTES = 32 * 1024 * 1024
_FRONT_COVER = 3
_FLAC_PICTURE = 6
_MP4_CONTAINERS = {b"moov", b"udta", b"ilst"}
_OGG_READ_LIMIT = MAX_PICTURE_BYTES * 2


def read_embedded_picture(path: str | Path) -> bytes | None:
    """The file's picture as encoded image bytes, or None. Never raises for a bad or missing file."""
    try:
        with open(path, "rb") as handle:
            start = handle.read(12)
            handle.seek(0)
            if start.startswith(b"ID3"):
                return _id3(handle)
            if start.startswith(b"fLaC"):
                return _flac(handle)
            if start[4:8] == b"ftyp":
                return _mp4(handle)
            if start.startswith(b"OggS"):
                return _ogg(handle)
    except (OSError, ValueError, IndexError, struct.error) as exc:
        log.debug("no embedded picture read: %s", exc)
    return None


def _usable(data: bytes) -> bytes | None:
    return data if 0 < len(data) <= MAX_PICTURE_BYTES else None


# -------------------------------------------------------------------- ID3v2
def _synchsafe(raw: bytes) -> int:
    return (raw[0] << 21) | (raw[1] << 14) | (raw[2] << 7) | raw[3]


def _id3(handle) -> bytes | None:  # type: ignore[no-untyped-def]
    header = handle.read(10)
    if len(header) < 10:
        return None
    version, flags = header[3], header[5]
    size = _synchsafe(header[6:10])
    tag = handle.read(min(size, MAX_PICTURE_BYTES + 1024 * 1024))
    if flags & 0x80 and version < 4:  # The whole tag was unsynchronised.
        tag = tag.replace(b"\xff\x00", b"\xff")
    position = 0
    if flags & 0x40 and version >= 3 and len(tag) >= 4:  # Extended header: step over it.
        extended = struct.unpack(">I", tag[:4])[0]
        position = _synchsafe(tag[:4]) if version == 4 else extended + 4
    best: bytes | None = None
    id_size, header_size = (3, 6) if version == 2 else (4, 10)
    while position + header_size <= len(tag):
        frame = tag[position : position + id_size]
        if not frame.strip(b"\0"):
            break
        if version == 2:
            length = int.from_bytes(tag[position + 3 : position + 6], "big")
        elif version == 4:
            length = _synchsafe(tag[position + 4 : position + 8])
        else:
            length = struct.unpack(">I", tag[position + 4 : position + 8])[0]
        body = tag[position + header_size : position + header_size + length]
        if frame in (b"APIC", b"PIC"):
            kind, picture = _id3_picture(body, frame == b"PIC")
            if picture and kind == _FRONT_COVER:
                return _usable(picture)
            best = best or picture
        position += header_size + length
    return _usable(best) if best else None


def _id3_picture(body: bytes, old_format: bool) -> tuple[int, bytes | None]:
    if len(body) < 6:
        return 0, None
    encoding = body[0]
    if old_format:  # ID3v2.2: a three-letter format instead of a MIME type.
        position = 4
    else:
        end = body.find(b"\0", 1)
        if end < 0:
            return 0, None
        position = end + 1
    kind = body[position]
    position += 1
    wide = encoding in (1, 2)  # UTF-16 descriptions end with two zero bytes on a character boundary.
    if wide:
        while position + 1 < len(body) and body[position : position + 2] != b"\0\0":
            position += 2
        position += 2
    else:
        end = body.find(b"\0", position)
        if end < 0:
            return kind, None
        position = end + 1
    return kind, body[position:] or None


# --------------------------------------------------------------------- FLAC
def _flac_picture_block(block: bytes) -> tuple[int, bytes | None]:
    kind, mime_length = struct.unpack(">II", block[:8])
    position = 8 + mime_length
    description_length = struct.unpack(">I", block[position : position + 4])[0]
    position += 4 + description_length + 16
    length = struct.unpack(">I", block[position : position + 4])[0]
    position += 4
    data = block[position : position + length]
    return kind, data if len(data) == length else None


def _flac(handle) -> bytes | None:  # type: ignore[no-untyped-def]
    handle.seek(4)
    best: bytes | None = None
    while True:
        header = handle.read(4)
        if len(header) < 4:
            break
        last = bool(header[0] & 0x80)
        kind = header[0] & 0x7F
        length = int.from_bytes(header[1:4], "big")
        if kind == _FLAC_PICTURE and length <= MAX_PICTURE_BYTES + 4096:
            picture_kind, picture = _flac_picture_block(handle.read(length))
            if picture and picture_kind == _FRONT_COVER:
                return _usable(picture)
            best = best or picture
        else:
            handle.seek(length, 1)
        if last:
            break
    return _usable(best) if best else None


# ---------------------------------------------------------------------- MP4
def _mp4_atoms(data: bytes, start: int, end: int):  # type: ignore[no-untyped-def]
    position = start
    while position + 8 <= end:
        size = struct.unpack(">I", data[position : position + 4])[0]
        name = data[position + 4 : position + 8]
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[position + 8 : position + 16])[0]
            header = 16
        elif size == 0:
            size = end - position
        if size < header or position + size > end:
            return
        yield name, position + header, position + size
        position += size


def _mp4_find_cover(data: bytes, start: int, end: int) -> bytes | None:
    for name, body, stop in _mp4_atoms(data, start, end):
        if name in _MP4_CONTAINERS:
            found = _mp4_find_cover(data, body, stop)
            if found:
                return found
        elif name == b"meta":
            found = _mp4_find_cover(data, body + 4, stop)  # meta has version and flags first.
            if found:
                return found
        elif name == b"covr":
            for inner, inner_body, inner_stop in _mp4_atoms(data, body, stop):
                if inner == b"data" and inner_stop - inner_body > 8:
                    return data[inner_body + 8 : inner_stop]
    return None


def _mp4(handle) -> bytes | None:  # type: ignore[no-untyped-def]
    size_of_file = handle.seek(0, 2)
    position = 0
    while position + 8 <= size_of_file:
        handle.seek(position)
        header = handle.read(16)
        size = struct.unpack(">I", header[:4])[0]
        name = header[4:8]
        if size == 1:
            size = struct.unpack(">Q", header[8:16])[0]
        elif size == 0:
            size = size_of_file - position
        if size < 8:
            return None
        if name == b"moov":
            if size > MAX_PICTURE_BYTES * 2:
                return None
            handle.seek(position)
            data = handle.read(size)
            cover = _mp4_find_cover(data, 8 if len(header) else 0, len(data))
            return _usable(cover) if cover else None
        position += size
    return None


# ---------------------------------------------------------------------- Ogg
def _ogg_packets(data: bytes):  # type: ignore[no-untyped-def]
    packet = bytearray()
    position = 0
    while data[position : position + 4] == b"OggS" and position + 27 <= len(data):
        segments = data[position + 26]
        table = data[position + 27 : position + 27 + segments]
        offset = position + 27 + segments
        for lacing in table:
            packet += data[offset : offset + lacing]
            offset += lacing
            if lacing < 255:
                yield bytes(packet)
                packet = bytearray()
        position = offset


def _ogg(handle) -> bytes | None:  # type: ignore[no-untyped-def]
    data = handle.read(_OGG_READ_LIMIT)
    for number, packet in enumerate(_ogg_packets(data)):
        if number > 2:
            return None
        if packet.startswith(b"\x03vorbis"):
            return _ogg_comments(packet[7:])
        if packet.startswith(b"OpusTags"):
            return _ogg_comments(packet[8:])
    return None


def _ogg_comments(body: bytes) -> bytes | None:
    vendor = struct.unpack("<I", body[:4])[0]
    position = 4 + vendor
    count = struct.unpack("<I", body[position : position + 4])[0]
    position += 4
    best: bytes | None = None
    for _ in range(count):
        length = struct.unpack("<I", body[position : position + 4])[0]
        position += 4
        comment = body[position : position + length]
        position += length
        name, _, value = comment.partition(b"=")
        if name.upper() != b"METADATA_BLOCK_PICTURE":
            continue
        try:
            kind, picture = _flac_picture_block(base64.b64decode(value))
        except (binascii.Error, struct.error):
            continue
        if picture and kind == _FRONT_COVER:
            return _usable(picture)
        best = best or picture
    return _usable(best) if best else None
