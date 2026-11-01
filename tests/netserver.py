"""Local HTTP server for M8 network tests: Range support, redirects, stalls and playlists.

Routes (besides files under ``root``, served with Range support):
* ``/redirect?to=<url>``   302 to any address (also file: and vlc:)
* ``/loop``                redirects to itself
* ``/stall``               reads the request and never answers
* ``/text?body=<text>``    200 with the given body (playlists, manifests)
* ``/big-playlist``        an #EXTM3U body larger than the proxy accepts
"""

from __future__ import annotations

import contextlib
import http.server
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class LocalServer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requests: list[str] = []
        self._stalled: list[object] = []
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: object) -> None:
                pass

            def do_HEAD(self) -> None:
                self.do_GET()

            def do_GET(self) -> None:
                server.requests.append(self.path)
                parts = urlsplit(self.path)
                query = parse_qs(parts.query)
                if parts.path == "/redirect":
                    self._send(302, b"", {"Location": query["to"][0]})
                elif parts.path == "/loop":
                    self._send(302, b"", {"Location": "/loop"})
                elif parts.path == "/stall":
                    server._stalled.append(self.connection)
                    time.sleep(60)
                elif parts.path == "/text":
                    self._send(200, query["body"][0].encode(), {"Content-Type": "text/plain"})
                elif parts.path == "/big-playlist":
                    self._send(200, b"#EXTM3U\n" + b"#" * (5 * 1024 * 1024), {})
                else:
                    self._file(server.root / parts.path.lstrip("/"))

            def _send(self, status: int, body: bytes, headers: dict[str, str]) -> None:
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    with contextlib.suppress(OSError):  # the client went away (seek, refusal)
                        self.wfile.write(body)

            def _file(self, path: Path) -> None:
                if not path.is_file() or server.root not in path.resolve().parents:
                    self._send(404, b"", {})
                    return
                data = path.read_bytes()
                start, end, status = 0, len(data) - 1, 200
                spec = self.headers.get("Range", "")
                if spec.startswith("bytes="):
                    first, _, last = spec[6:].partition("-")
                    start = int(first or 0)
                    end = min(int(last) if last else len(data) - 1, len(data) - 1)
                    status = 206
                    if start >= len(data):
                        self._send(416, b"", {"Content-Range": f"bytes */{len(data)}"})
                        return
                headers = {"Accept-Ranges": "bytes", "Content-Type": "application/octet-stream"}
                if status == 206:
                    headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
                self._send(status, data[start : end + 1], headers)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = int(self.httpd.server_address[1])
        self.base = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
