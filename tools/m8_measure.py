"""M8 measurements: seek-preview latency per file, and stream-proxy throughput.

Previews: open time, then 20 seeks to random times (fixed seed); median and worst latency.
Proxy: reads a local file over HTTP from 127.0.0.1 directly and through the stream proxy.
Writes JSON to tools/engine-benchmark/results/m8_measure.json (or the path given).
Usage:  python tools/m8_measure.py [out.json]
"""

from __future__ import annotations

import http.client
import json
import random
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from babarify_frame.playback.adapters.libvlc_preview import LibVlcPreview
from babarify_frame.playback.stream_proxy import StreamProxy
from netserver import LocalServer

ROOT = Path(__file__).resolve().parents[1]

MEDIA = ROOT / "tests" / "fixtures" / "media" / "generated"
FILES = ("h264_1080p30_aac.mp4", "hevc_2160p30_aac.mkv", "av1_1080p30_opus.mkv", "e_long_1h_240p.mkv")


def preview_latency() -> list[dict[str, object]]:
    rows = []
    preview = LibVlcPreview()
    rng = random.Random(8)
    for name in FILES:
        path = MEDIA / name
        if not path.exists():
            continue
        started = time.perf_counter()
        ok = preview.open(str(path))
        opened_ms = round((time.perf_counter() - started) * 1000)
        latencies, missing = [], 0
        duration = 3_600_000 if "1h" in name else 10_000
        for _ in range(20):
            target = rng.randrange(0, duration - 500)
            t = time.perf_counter()
            frame = preview.frame_at(target)
            if frame is None:
                missing += 1
            else:
                latencies.append((time.perf_counter() - t) * 1000)
        rows.append({
            "file": name, "opened": ok, "open_ms": opened_ms, "frames": len(latencies), "missing": missing,
            "median_ms": round(statistics.median(latencies)) if latencies else None,
            "worst_ms": round(max(latencies)) if latencies else None,
        })  # fmt: skip
        print(rows[-1])
    preview.close()
    return rows


def read_all(url: str) -> tuple[int, float]:
    parts = urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname or "", parts.port, timeout=30)
    started = time.perf_counter()
    conn.request("GET", parts.path + (f"?{parts.query}" if parts.query else ""))
    response = conn.getresponse()
    size = 0
    while chunk := response.read(256 * 1024):
        size += len(chunk)
    conn.close()
    return size, time.perf_counter() - started


def proxy_throughput() -> dict[str, object]:
    server = LocalServer(MEDIA)
    proxy = StreamProxy()
    name = "hevc_2160p30_aac.mkv"
    direct = [read_all(server.url(name)) for _ in range(3)]
    proxied = [read_all(proxy.wrap(server.url(name))) for _ in range(3)]
    server.close()
    proxy.close()
    size = direct[0][0]
    result = {
        "file": name,
        "bytes": size,
        "direct_mb_s": round(size / min(t for _, t in direct) / 1e6),
        "proxy_mb_s": round(size / min(t for _, t in proxied) / 1e6),
        "same_size": all(s == size for s, _ in proxied),
    }
    print(result)
    return result


def main() -> int:
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "tools" / "engine-benchmark" / "results" / "m8_measure.json"
    )
    data = {"previews": preview_latency(), "proxy": proxy_throughput()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
