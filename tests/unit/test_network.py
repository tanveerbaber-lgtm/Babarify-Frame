"""M8: stream address rules (core.network) and the URI gate in the engine contract."""

from __future__ import annotations

import pytest

from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.network import (
    MAX_URL_LENGTH,
    is_network_uri,
    stream_display_name,
    uri_scheme,
    validate_stream_url,
)
from babarify_frame.playback.contracts import normalize_local_uri


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://example.com/live/a.m3u8", "https://example.com/live/a.m3u8"),
        ("  HTTP://Example.COM:8080/a.mp4?token=1  ", "http://example.com:8080/a.mp4?token=1"),
        ("http://example.com", "http://example.com/"),
        ("rtsp://192.168.1.20:554/stream1", "rtsp://192.168.1.20:554/stream1"),
        ("http://[::1]:8000/a.ts", "http://[::1]:8000/a.ts"),
        ("https://example.com/a.mp4#t=10", "https://example.com/a.mp4"),  # fragment dropped
        ("https://bücher.example/a.mp3", "https://bücher.example/a.mp3"),
    ],
)
def test_valid_addresses_are_normalised(text: str, expected: str) -> None:
    assert validate_stream_url(text) == expected


@pytest.mark.parametrize(
    ("text", "code", "words"),
    [
        ("", ErrorCode.INVALID_ARGUMENT, "enter"),
        ("example.com/a.mp4", ErrorCode.INVALID_ARGUMENT, "must start"),
        ("file:///C:/Windows/win.ini", ErrorCode.UNSUPPORTED, "'file'"),
        ("smb://server/share/a.mkv", ErrorCode.UNSUPPORTED, "'smb'"),
        ("ftp://example.com/a.mp4", ErrorCode.UNSUPPORTED, "'ftp'"),
        ("vlc://quit", ErrorCode.UNSUPPORTED, "'vlc'"),
        ("dshow://", ErrorCode.UNSUPPORTED, "'dshow'"),
        ("screen://", ErrorCode.UNSUPPORTED, "'screen'"),
        ("udp://@239.0.0.1:1234", ErrorCode.UNSUPPORTED, "'udp'"),
        ("javascript://alert(1)", ErrorCode.UNSUPPORTED, "'javascript'"),
        ("http://user:secret@example.com/a.mp4", ErrorCode.INVALID_ARGUMENT, "password"),
        ("http://user@example.com/a.mp4", ErrorCode.INVALID_ARGUMENT, "password"),
        ("http://example.com/a b.mp4", ErrorCode.INVALID_ARGUMENT, "spaces"),
        ("http://example.com/a\x00.mp4", ErrorCode.INVALID_ARGUMENT, "control"),
        ("http://example.com/a\r\nHost: evil", ErrorCode.INVALID_ARGUMENT, "spaces"),
        ("http:///a.mp4", ErrorCode.INVALID_ARGUMENT, "server name"),
        ("http://example.com:99999/a", ErrorCode.INVALID_ARGUMENT, "not valid"),
        ("http://example.com:0/a", ErrorCode.INVALID_ARGUMENT, "port 0"),
        ("http://-bad.example/a", ErrorCode.INVALID_ARGUMENT, "server name"),
        ("http://exa%6dple.com/a", ErrorCode.INVALID_ARGUMENT, "server name"),
        ("http://" + "a" * MAX_URL_LENGTH + ".com/", ErrorCode.INVALID_ARGUMENT, "longer"),
    ],
)
def test_untrusted_addresses_are_refused_with_a_reason(text: str, code: ErrorCode, words: str) -> None:
    with pytest.raises(PlaybackError) as exc:
        validate_stream_url(text)
    assert exc.value.code is code
    assert words in exc.value.detail


def test_engine_scheme_list_limits_streams() -> None:
    assert validate_stream_url("https://example.com/a", frozenset({"https"}))
    with pytest.raises(PlaybackError) as exc:
        validate_stream_url("rtsp://example.com/a", frozenset({"https"}))
    assert exc.value.code is ErrorCode.UNSUPPORTED
    # An engine without network support (mpv today) refuses every stream at the contract.
    with pytest.raises(PlaybackError) as exc:
        normalize_local_uri("https://example.com/a.mp4", frozenset({"file"}))
    assert exc.value.code is ErrorCode.UNSUPPORTED and "none" in exc.value.detail


def test_contract_validates_network_addresses() -> None:
    allowed = frozenset({"file", "http", "https", "rtsp"})
    assert normalize_local_uri("HTTPS://Example.com/a#x", allowed) == "https://example.com/a"
    with pytest.raises(PlaybackError):
        normalize_local_uri("http://u:p@example.com/a", allowed)


def test_scheme_helpers() -> None:
    assert uri_scheme(r"C:\Videos\a.mp4") == ""
    assert uri_scheme("file:///C:/a.mp4") == "file"
    assert uri_scheme("HTTPS://x/a") == "https"
    assert is_network_uri("rtsp://cam/stream") and not is_network_uri("mock://clip")


def test_display_name_never_shows_the_query() -> None:
    name = stream_display_name("https://cdn.example.com/live/show%20one.m3u8?token=SECRET")
    assert name == "show one.m3u8 (cdn.example.com)"
    assert stream_display_name("http://radio.example.com/") == "radio.example.com"
