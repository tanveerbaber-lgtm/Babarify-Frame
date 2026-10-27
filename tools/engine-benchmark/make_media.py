"""Generate the synthetic benchmark corpus with FFmpeg.

All media is produced from FFmpeg's built-in test sources (testsrc2, sine),
so there are no copyright or provenance questions. Output goes to the
git-ignored ``tests/fixtures/media/generated/`` folder and a manifest with
the exact commands, FFmpeg version and SHA-256 checksums is written next to
this script.

Usage:  python tools/engine-benchmark/make_media.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "fixtures" / "media" / "generated"
MANIFEST = Path(__file__).resolve().parent / "media-manifest.json"

SRT_ENG = """1
00:00:01,000 --> 00:00:04,000
Babarify Frame subtitle test (English)

2
00:00:06,000 --> 00:00:09,000
Second English cue
"""

ASS_FRA = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Alignment
Style: Default,Arial,40,&H0022C55E,&H00000000,1,2,2

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:02.00,0:00:05.00,Default,Sous-titre de test (français)
"""

VIDEO = "testsrc2=size={w}x{h}:rate={fps}"
# -60 dB: real audio decode/output path, inaudible during benchmark runs.
TONE = "sine=frequency={f}:sample_rate=48000,volume=-60dB"

# name -> (ffmpeg args after inputs, description, expected properties)
CLIPS: dict[str, dict[str, object]] = {
    "h264_1080p30_aac.mp4": {
        "inputs": [VIDEO.format(w=1920, h=1080, fps=30), TONE.format(f=440)],
        "args": [
            "-t",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
        ],
        "expect": {
            "video": "h264",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "audio": "aac",
            "duration_s": 30,
        },
    },
    "hevc_2160p30_aac.mkv": {
        "inputs": [VIDEO.format(w=3840, h=2160, fps=30), TONE.format(f=440)],
        "args": [
            "-t",
            "20",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-x265-params",
            "log-level=error",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
        ],
        "expect": {
            "video": "hevc",
            "width": 3840,
            "height": 2160,
            "fps": 30,
            "audio": "aac",
            "duration_s": 20,
        },
    },
    "vp9_1080p30_opus.webm": {
        "inputs": [VIDEO.format(w=1920, h=1080, fps=30), TONE.format(f=440)],
        "args": [
            "-t",
            "20",
            "-c:v",
            "libvpx-vp9",
            "-deadline",
            "realtime",
            "-cpu-used",
            "8",
            "-b:v",
            "4M",
            "-row-mt",
            "1",
            "-c:a",
            "libopus",
            "-b:a",
            "96k",
        ],
        "expect": {
            "video": "vp9",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "audio": "opus",
            "duration_s": 20,
        },
    },
    "av1_1080p30_opus.mkv": {
        "inputs": [VIDEO.format(w=1920, h=1080, fps=30), TONE.format(f=440)],
        "args": [
            "-t",
            "20",
            "-c:v",
            "libsvtav1",
            "-preset",
            "12",
            "-crf",
            "35",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "libopus",
            "-b:a",
            "96k",
        ],
        "expect": {
            "video": "av1",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "audio": "opus",
            "duration_s": 20,
        },
    },
    "multitrack_720p.mkv": {
        "inputs": [VIDEO.format(w=1280, h=720, fps=25), TONE.format(f=440), TONE.format(f=880)],
        "subtitle_files": ["eng.srt", "fra.ass"],
        "args": [
            "-t",
            "20",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:a",
            "-map",
            "3:s",
            "-map",
            "4:s",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "26",
            "-pix_fmt",
            "yuv420p",
            "-c:a:0",
            "aac",
            "-c:a:1",
            "ac3",
            "-c:s:0",
            "srt",
            "-c:s:1",
            "ass",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:0",
            "title=English tone",
            "-metadata:s:a:1",
            "language=fra",
            "-metadata:s:a:1",
            "title=French tone",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:s:1",
            "language=fra",
        ],
        "expect": {
            "video": "h264",
            "width": 1280,
            "height": 720,
            "fps": 25,
            "audio_tracks": 2,
            "subtitle_tracks": 2,
            "duration_s": 20,
        },
    },
}


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="regenerate existing files")
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 2
    version = subprocess.run([ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True).stdout
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eng.srt").write_text(SRT_ENG, encoding="utf-8")
    (OUT / "fra.ass").write_text(ASS_FRA, encoding="utf-8")

    entries = []
    for name, spec in CLIPS.items():
        target = OUT / name
        cmd = [ffmpeg, "-hide_banner", "-y"]
        for source in spec["inputs"]:  # type: ignore[attr-defined]
            cmd += ["-f", "lavfi", "-i", source]
        for sub in spec.get("subtitle_files", []):  # type: ignore[attr-defined]
            cmd += ["-i", str(OUT / sub)]
        cmd += [*spec["args"], str(target)]  # type: ignore[misc]
        if args.force or not target.exists():
            print(f"generating {name} ...", flush=True)
            run(cmd)
        entries.append(
            {
                "file": name,
                "kind": "valid",
                "expect": spec["expect"],
                "command": " ".join(Path(c).name if c == ffmpeg else c for c in cmd),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )

    # Failure fixtures: an MP4 whose index (moov at the end) is cut off, and a text file named .mp4.
    truncated_src = OUT / "_truncate_source.mp4"
    if args.force or not (OUT / "truncated.mp4").exists():
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                VIDEO.format(w=640, h=360, fps=30),
                "-t",
                "5",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                str(truncated_src),
            ]
        )
        data = truncated_src.read_bytes()
        (OUT / "truncated.mp4").write_bytes(data[: len(data) // 2])
        truncated_src.unlink()
    (OUT / "not_media.mp4").write_text("This is not a video file.\n", encoding="utf-8")
    for name, why in [
        ("truncated.mp4", "first half of an MP4 with its moov index at the end"),
        ("not_media.mp4", "plain text with a .mp4 extension"),
    ]:
        path = OUT / name
        entries.append(
            {
                "file": name,
                "kind": "invalid",
                "expect": {"opens": False},
                "description": why,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    MANIFEST.write_text(
        json.dumps(
            {
                "generator": "tools/engine-benchmark/make_media.py",
                "output_dir": str(OUT.relative_to(ROOT)).replace("\\", "/"),
                "provenance": (
                    "Synthetic: FFmpeg lavfi testsrc2 video and sine audio. No third-party content."
                ),
                "ffmpeg_version": version.splitlines()[0],
                "note": "Checksums are for this FFmpeg build; other builds produce different bytes.",
                "files": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(entries)} files and {MANIFEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
