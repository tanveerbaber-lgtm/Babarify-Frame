"""Network stream addresses (M8). Every address typed, pasted or found in a playlist is untrusted.

Rules (see docs/architecture/overview.md#network-streams-m8):
* Only http, https and rtsp. Everything else (file, smb, ftp, udp, mms, rtmp, vlc, dshow,
  screen, ...) is refused, so an address can never select a local file, a device or a
  libVLC control URL.
* A host is required; user names and passwords in the address are refused (they would be
  stored in history and shown in the title bar).
* No whitespace or control characters; at most MAX_URL_LENGTH characters.
* The fragment (#...) is dropped: it is never sent to a server, and libVLC reads it as a
  title/chapter selector.
"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit, urlunsplit

from babarify_frame.core.errors import ErrorCode, PlaybackError

STREAM_SCHEMES = frozenset({"http", "https", "rtsp"})
MAX_URL_LENGTH = 2048


def uri_scheme(uri: str) -> str:
    """Lower-case scheme of a URI; "" for plain paths (a one-letter scheme is a Windows drive)."""
    scheme = urlsplit(uri).scheme.lower() if "://" in uri or uri[:5].lower() == "file:" else ""
    return scheme if len(scheme) > 1 else ""


def is_network_uri(uri: str) -> bool:
    return uri_scheme(uri) in STREAM_SCHEMES


def validate_stream_url(text: str, allowed: frozenset[str] = STREAM_SCHEMES) -> str:
    """Return the canonical form of a stream address, or raise PlaybackError with a reason
    worded for the user."""
    if not isinstance(text, str):
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "the address must be text")
    url = text.strip()
    if not url:
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "enter a stream address")
    if len(url) > MAX_URL_LENGTH:
        raise PlaybackError(
            ErrorCode.INVALID_ARGUMENT, f"the address is longer than {MAX_URL_LENGTH} characters"
        )
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "the address contains spaces or control characters")
    try:
        parts = urlsplit(url)
        port = parts.port  # raises ValueError for a bad port
    except ValueError as exc:
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, f"the address is not valid ({exc})") from exc
    scheme = parts.scheme.lower()
    if "://" not in url or not scheme:
        raise PlaybackError(
            ErrorCode.INVALID_ARGUMENT, "the address must start with http://, https:// or rtsp://"
        )
    if scheme not in allowed:
        supported = ", ".join(f"{s}://" for s in sorted(allowed)) or "none"
        raise PlaybackError(
            ErrorCode.UNSUPPORTED, f"'{scheme}' addresses are not supported (supported: {supported})"
        )
    if parts.username is not None or parts.password is not None:
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "remove the user name and password from the address")
    host = parts.hostname or ""
    if not host:
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "the address has no server name")
    if host.startswith(("-", ".")) or any(c in host for c in "\\%"):
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "the server name is not valid")
    if not (":" in host or _valid_hostname(host)):  # ":" = an IPv6 literal, checked by urlsplit
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "the server name is not valid")
    if port == 0:
        raise PlaybackError(ErrorCode.INVALID_ARGUMENT, "port 0 is not valid")
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def _valid_hostname(host: str) -> bool:
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_host.rstrip(".").split(".")
    return len(ascii_host) <= 253 and all(
        0 < len(label) <= 63 and all(c.isalnum() or c in "-_" for c in label) for label in labels
    )


def stream_display_name(url: str) -> str:
    """Short name for titles and history: host and last path part, never the query string
    (it often carries access tokens)."""
    parts = urlsplit(url)
    name = unquote(parts.path.rstrip("/").rsplit("/", 1)[-1])
    host = parts.hostname or url
    return f"{name} ({host})" if name else host
