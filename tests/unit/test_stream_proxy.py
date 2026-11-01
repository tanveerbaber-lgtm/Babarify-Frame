"""M8: the loopback stream proxy, tested over real sockets without libVLC."""

from __future__ import annotations

import http.client
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlsplit

import pytest

import babarify_frame.playback.stream_proxy as sp
from babarify_frame.core.errors import PlaybackError
from babarify_frame.playback.stream_proxy import REMOVED, StreamProxy, rewrite_playlist
from netserver import LocalServer


@pytest.fixture
def server(tmp_path: Path) -> Iterator[LocalServer]:
    (tmp_path / "clip.bin").write_bytes(bytes(range(256)) * 400)  # 102,400 bytes
    (tmp_path / "live.m3u8").write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
        "#EXTINF:2,\nseg0.ts\n#EXTINF:2,\nhttp://other.example/seg1.ts\n"
        "#EXTINF:2,\nfile:///C:/Windows/win.ini\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    srv = LocalServer(tmp_path)
    yield srv
    srv.close()


@pytest.fixture
def proxy() -> Iterator[StreamProxy]:
    p = StreamProxy()
    yield p
    p.close()


def get(local: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    parts = urlsplit(local)
    conn = http.client.HTTPConnection(parts.hostname or "", parts.port, timeout=30)
    conn.request("GET", parts.path + "?" + parts.query, headers=headers or {})
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, {k.lower(): v for k, v in response.getheaders()}, body


# ------------------------------------------------------------ rewriting
def test_rewrite_points_entries_at_the_proxy_and_removes_other_schemes() -> None:
    text = (
        "#EXTM3U\n#EXTINF:2,\nseg0.ts\n"
        '#EXT-X-MAP:URI="init.mp4"\n'
        '#EXT-X-KEY:METHOD=AES-128,URI="file:///C:/key"\n'
        "vlc://quit\nhttps://cdn.example/a.ts\n# a comment\n\n"
    )
    out, removed = rewrite_playlist(text, "http://host.example/live/index.m3u8", lambda u: f"P[{u}]")
    lines = out.splitlines()
    assert "P[http://host.example/live/seg0.ts]" in lines
    assert '#EXT-X-MAP:URI="P[http://host.example/live/init.mp4]"' in lines
    assert "P[https://cdn.example/a.ts]" in lines
    assert lines.count(REMOVED) == 2 and removed == 2  # the file: key and vlc://quit
    assert "# a comment" in lines
    assert "file:" not in out and "vlc:" not in out


# ------------------------------------------------------------ serving
def test_token_is_required(proxy: StreamProxy) -> None:
    status, _, _ = get(f"http://127.0.0.1:{proxy.port}/wrongtoken/s?u=" + quote("http://example.com/"))
    assert status == 403


def test_wrap_refuses_non_web_addresses(proxy: StreamProxy) -> None:
    with pytest.raises(PlaybackError):
        proxy.wrap("file:///C:/Windows/win.ini")
    local = proxy.wrap("https://Example.com/a.mp4")
    assert proxy.unwrap(local) == "https://example.com/a.mp4"
    assert proxy.unwrap("http://elsewhere/a") is None


def test_file_is_relayed_with_ranges(proxy: StreamProxy, server: LocalServer) -> None:
    status, headers, body = get(proxy.wrap(server.url("clip.bin")))
    assert status == 200 and len(body) == 102_400 and headers["accept-ranges"] == "bytes"
    status, headers, body = get(proxy.wrap(server.url("clip.bin")), {"Range": "bytes=1000-1099"})
    assert status == 206 and body == (bytes(range(256)) * 400)[1000:1100]
    assert headers["content-range"] == "bytes 1000-1099/102400"


def test_redirect_to_a_local_file_is_refused(proxy: StreamProxy, server: LocalServer, tmp_path: Path) -> None:
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"local data")
    url = server.url("redirect?to=" + quote(secret.as_uri(), safe=""))
    status, _, body = get(proxy.wrap(url))
    assert status == 502 and b"local data" not in body
    assert "non-web address (file:)" in proxy.failures_since(0)[-1]


@pytest.mark.parametrize("target", ["vlc://quit", "smb://server/share/a.mkv", "dshow://"])
def test_redirects_to_other_schemes_are_refused(proxy: StreamProxy, server: LocalServer, target: str) -> None:
    status, _, _ = get(proxy.wrap(server.url("redirect?to=" + quote(target, safe=""))))
    assert status == 502


def test_web_redirects_are_followed(proxy: StreamProxy, server: LocalServer) -> None:
    url = server.url("redirect?to=" + quote("/clip.bin", safe=""))
    status, _, body = get(proxy.wrap(url))
    assert status == 200 and len(body) == 102_400


def test_redirect_loops_stop(proxy: StreamProxy, server: LocalServer) -> None:
    status, _, _ = get(proxy.wrap(server.url("loop")))
    assert status == 502 and "redirects" in proxy.failures_since(0)[-1]


def test_errors_are_passed_on_with_a_reason(proxy: StreamProxy, server: LocalServer) -> None:
    status, _, _ = get(proxy.wrap(server.url("missing.mp4")))
    assert status == 404
    assert proxy.failures_since(0)[-1] == "the server answered 404 Not Found"


def test_unknown_host_and_refused_connection(proxy: StreamProxy) -> None:
    status, _, _ = get(proxy.wrap("http://does-not-exist.invalid/a.mp4"))
    assert status == 502 and "could not be found" in proxy.failures_since(0)[-1]
    status, _, _ = get(proxy.wrap("http://127.0.0.1:9/a.mp4"))  # discard port: nothing listens
    assert status == 502 and "could not connect" in proxy.failures_since(0)[-1]


def test_stalled_server_times_out(
    proxy: StreamProxy, server: LocalServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sp, "READ_TIMEOUT_S", 1.0)
    status, _, _ = get(proxy.wrap(server.url("stall")))
    assert status == 504 and "no answer" in proxy.failures_since(0)[-1]


def test_hls_playlist_is_rewritten(proxy: StreamProxy, server: LocalServer) -> None:
    status, headers, body = get(proxy.wrap(server.url("live.m3u8")))
    text = body.decode()
    assert status == 200 and headers["content-type"] == "application/vnd.apple.mpegurl"
    entries = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(entries) == 2 and all(e.startswith(proxy.prefix) for e in entries)
    assert proxy.unwrap(entries[0]) == server.url("seg0.ts")
    assert proxy.unwrap(entries[1]) == "http://other.example/seg1.ts"
    assert f'URI="{proxy.prefix}' in text  # the key goes through the proxy too
    assert "win.ini" not in text and proxy.removed_since(0) == 1


def test_plain_m3u_is_not_labelled_hls(proxy: StreamProxy, server: LocalServer) -> None:
    body = quote("#EXTM3U\nhttp://radio.example/stream.mp3\n", safe="")
    status, headers, _ = get(proxy.wrap(server.url("text?body=" + body)))
    assert status == 200 and headers["content-type"] == "audio/x-mpegurl"


def test_dash_manifest_is_refused(proxy: StreamProxy, server: LocalServer) -> None:
    body = quote('<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011"></MPD>', safe="")
    status, _, _ = get(proxy.wrap(server.url("text?body=" + body)))
    assert status == 415 and "DASH" in proxy.failures_since(0)[-1]


def test_oversized_playlist_is_refused(proxy: StreamProxy, server: LocalServer) -> None:
    status, _, _ = get(proxy.wrap(server.url("big-playlist")))
    assert status == 413
