"""Loopback proxy for HTTP(S) streams (M8). libVLC never fetches a web address itself.

Why: the M8 spike showed that libVLC 3 follows an HTTP redirect to *any* scheme its plugins
know, including ``file:`` (a web server could make the player open a local file, or a
``\\\\server\\share`` path, which makes Windows connect out over SMB). HLS manifests can
likewise name ``file:`` segments or keys. libVLC has no option to restrict this.

So libVLC is given ``http://127.0.0.1:<port>/<token>/s?u=<address>``, and this proxy:
* fetches the address itself (certificate checks on, connect 10 s, read 20 s), following at
  most 5 redirects and only to http/https addresses that pass ``validate_stream_url``;
* rewrites HLS/M3U playlists so every entry and ``URI="..."`` attribute points back at the
  proxy; entries with any other scheme are removed and counted;
* refuses DASH/Smooth Streaming manifests (XML it does not rewrite) with 415;
* answers failures with an HTTP error, so libVLC fails quickly, and records a reason for the
  engine to show.
It listens on 127.0.0.1 only, and every path must carry a random per-process token, so other
local programs cannot use it as an open proxy. libVLC never sees a redirect from it.
"""

from __future__ import annotations

import http.client
import http.server
import logging
import re
import secrets
import socket
import ssl
import threading
import time
from collections import deque
from collections.abc import Callable
from urllib.parse import parse_qs, quote, urljoin, urlsplit

from babarify_frame import __version__
from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.network import validate_stream_url

log = logging.getLogger(__name__)

WEB_SCHEMES = frozenset({"http", "https"})
CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 20.0
MAX_REDIRECTS = 5
MAX_PLAYLIST_BYTES = 4 * 1024 * 1024
CHUNK = 64 * 1024
USER_AGENT = f"BabarifyMediaPlayer/{__version__} (libVLC)"
# Request headers passed on to the server, and response headers passed back to libVLC.
_REQUEST_HEADERS = ("Range", "Icy-MetaData", "Accept")
_RESPONSE_HEADERS = (
    "Content-Type",
    "Content-Length",
    "Content-Range",
    "Accept-Ranges",
    "Last-Modified",
    "ETag",
)
_URI_ATTR = re.compile(r'URI="([^"]*)"')
REMOVED = "# babarify: entry removed (not an http/https address)"


class ProxyRefusal(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _web_url(url: str) -> str | None:
    try:
        return validate_stream_url(url, WEB_SCHEMES)
    except PlaybackError:
        return None


def is_playlist(head: bytes) -> bool:
    return head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"#EXTM3U")


def is_unsupported_manifest(head: bytes) -> bool:
    start = head.lstrip(b"\xef\xbb\xbf \t\r\n")[:4096]
    return start.startswith(b"<") and (b"<MPD" in start or b"<SmoothStreamingMedia" in start)


def rewrite_playlist(text: str, base_url: str, wrap: Callable[[str], str]) -> tuple[str, int]:
    """Point every playlist entry and URI attribute at the proxy. Returns (text, removed)."""
    removed = 0
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
        elif stripped.startswith("#"):
            if not stripped.startswith("#EXT") or 'URI="' not in stripped:
                out.append(line)
                continue
            bad = False

            def attr(match: re.Match[str]) -> str:
                nonlocal bad
                target = _web_url(urljoin(base_url, match.group(1)))
                if target is None:
                    bad = True
                    return match.group(0)
                return f'URI="{wrap(target)}"'

            rewritten = _URI_ATTR.sub(attr, stripped)
            if bad:
                removed += 1
                out.append(REMOVED)
            else:
                out.append(rewritten)
        else:
            target = _web_url(urljoin(base_url, stripped))
            if target is None:
                removed += 1
                out.append(REMOVED)
            else:
                out.append(wrap(target))
    return "\n".join(out) + "\n", removed


class StreamProxy:
    """One per process, started on first use (``get_proxy``)."""

    def __init__(self) -> None:
        self.token = secrets.token_hex(16)
        self._failures: deque[tuple[float, str, str]] = deque(maxlen=50)
        self._removed: deque[tuple[float, int]] = deque(maxlen=50)
        self._ssl = ssl.create_default_context()
        proxy = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                log.debug("stream proxy: " + fmt, *args)

            def do_GET(self) -> None:
                proxy._handle(self, "GET")

            def do_HEAD(self) -> None:
                proxy._handle(self, "HEAD")

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, name="stream-proxy", daemon=True)
        self._thread.start()

    @property
    def prefix(self) -> str:
        return f"http://127.0.0.1:{self.port}/{self.token}/s?u="

    def wrap(self, url: str) -> str:
        """Proxy address for a web address (validated again here)."""
        target = _web_url(url)
        if target is None:
            raise PlaybackError(ErrorCode.UNSUPPORTED, f"not an http/https address: {url[:80]}")
        return self.prefix + quote(target, safe="")

    def unwrap(self, local: str) -> str | None:
        """The web address behind one of this proxy's addresses, else None."""
        if not local.startswith(self.prefix):
            return None
        values = parse_qs(urlsplit(local).query).get("u")
        return values[0] if values else None

    def failures_since(self, since: float) -> list[str]:
        return [reason for when, _url, reason in list(self._failures) if when >= since]

    def removed_since(self, since: float) -> int:
        return sum(n for when, n in list(self._removed) if when >= since)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # ---------------------------------------------------------------- serving
    def _handle(self, request: http.server.BaseHTTPRequestHandler, method: str) -> None:
        parts = urlsplit(request.path)
        if parts.path != f"/{self.token}/s":
            request.send_error(403)
            return
        values = parse_qs(parts.query).get("u")
        url = _web_url(values[0]) if values else None
        if url is None:
            self._fail(request, ProxyRefusal(400, "not an http/https address"), values[0] if values else "")
            return
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        for name in _REQUEST_HEADERS:
            if (value := request.headers.get(name)) is not None:
                headers[name] = value
        try:
            final_url, conn, response = self._fetch(url, method, headers)
        except ProxyRefusal as refusal:
            self._fail(request, refusal, url)
            return
        try:
            self._relay(request, method, final_url, response)
        except (ConnectionError, TimeoutError, OSError):
            pass  # the player closed the connection (seek, stop) or the server stalled
        finally:
            conn.close()

    def _fail(self, request: http.server.BaseHTTPRequestHandler, refusal: ProxyRefusal, url: str) -> None:
        self._failures.append((time.monotonic(), url, refusal.reason))
        log.info("stream proxy refused %s: %s", url[:120], refusal.reason)
        try:
            request.send_response(refusal.status)
            request.send_header("Content-Length", "0")
            request.end_headers()
        except OSError:
            pass

    def _fetch(
        self, url: str, method: str, headers: dict[str, str]
    ) -> tuple[str, http.client.HTTPConnection, http.client.HTTPResponse]:
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            port = parts.port
            host = parts.hostname or ""
            conn: http.client.HTTPConnection
            if parts.scheme == "https":
                conn = http.client.HTTPSConnection(host, port, timeout=CONNECT_TIMEOUT_S, context=self._ssl)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=CONNECT_TIMEOUT_S)
            target = parts.path + (f"?{parts.query}" if parts.query else "")
            try:
                conn.connect()
                assert conn.sock is not None
                conn.sock.settimeout(READ_TIMEOUT_S)
                conn.request(method, target or "/", headers=headers)
                response = conn.getresponse()
            except ssl.SSLCertVerificationError as exc:
                conn.close()
                raise ProxyRefusal(
                    502, f"the server's certificate is not trusted ({exc.verify_message})"
                ) from exc
            except TimeoutError as exc:
                conn.close()
                raise ProxyRefusal(504, f"no answer from {host} within {READ_TIMEOUT_S:.0f} s") from exc
            except socket.gaierror as exc:
                conn.close()
                raise ProxyRefusal(502, f"the server name {host} could not be found") from exc
            except (OSError, http.client.HTTPException) as exc:
                conn.close()
                raise ProxyRefusal(502, f"could not connect to {host}: {exc}") from exc
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location") or ""
                conn.close()
                next_url = _web_url(urljoin(url, location))
                if next_url is None:
                    scheme = urlsplit(urljoin(url, location)).scheme or "unknown"
                    raise ProxyRefusal(
                        502, f"the server redirected to a non-web address ({scheme}:), which is not allowed"
                    )
                url = next_url
                continue
            if response.status >= 400 and response.status != 416:
                conn.close()
                raise ProxyRefusal(
                    response.status, f"the server answered {response.status} {response.reason}"
                )
            return url, conn, response
        raise ProxyRefusal(502, f"more than {MAX_REDIRECTS} redirects")

    def _relay(
        self,
        request: http.server.BaseHTTPRequestHandler,
        method: str,
        final_url: str,
        response: http.client.HTTPResponse,
    ) -> None:
        head = response.read1(CHUNK) if method == "GET" else b""
        if head and is_unsupported_manifest(head):
            refusal = ProxyRefusal(415, "DASH and Smooth Streaming manifests are not supported")
            self._fail(request, refusal, final_url)
            return
        if head and is_playlist(head):
            body = head
            while len(body) <= MAX_PLAYLIST_BYTES:
                more = response.read1(CHUNK)
                if not more:
                    break
                body += more
            if len(body) > MAX_PLAYLIST_BYTES:
                self._fail(request, ProxyRefusal(413, "the playlist is too large"), final_url)
                return
            text, removed = rewrite_playlist(body.decode("utf-8", "replace"), final_url, self.wrap)
            if removed:
                self._removed.append((time.monotonic(), removed))
            data = text.encode("utf-8")
            # HLS (has #EXT-X- tags) for libVLC's adaptive demuxer; a plain M3U playlist must not
            # be labelled HLS, or libVLC treats it as a broken stream instead of a list (M8).
            hls = "#EXT-X-" in text
            request.send_response(200)
            request.send_header("Content-Type", "application/vnd.apple.mpegurl" if hls else "audio/x-mpegurl")
            request.send_header("Content-Length", str(len(data)))
            request.end_headers()
            request.wfile.write(data)
            return
        request.send_response(response.status)
        for name in _RESPONSE_HEADERS:
            if (value := response.getheader(name)) is not None:
                request.send_header(name, value)
        for name, value in response.getheaders():
            if name.lower().startswith("icy-"):
                request.send_header(name, value)
        request.end_headers()
        if method == "HEAD":
            return
        while head:
            request.wfile.write(head)
            head = response.read1(CHUNK)


_proxy: StreamProxy | None = None
_proxy_lock = threading.Lock()


def get_proxy() -> StreamProxy:
    global _proxy
    with _proxy_lock:
        if _proxy is None:
            _proxy = StreamProxy()
        return _proxy
