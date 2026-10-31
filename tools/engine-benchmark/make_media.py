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


for spec in CLIPS.values():
    spec["set"] = "benchmark"


def _clip(video: str | None, tones: list[int], args: str, expect: dict[str, object]) -> dict[str, object]:
    inputs = ([video] if video else []) + [TONE.format(f=f) for f in tones]
    return {"inputs": inputs, "args": args.split(), "expect": expect, "set": "corpus"}


# M2 playback corpus: common containers and codecs, 8-10 s each. Codec names in "expect"
# use FFmpeg/ffprobe vocabulary, which is also what the engine adapters report.
_V720 = VIDEO.format(w=1280, h=720, fps=25)
_X264 = "-c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p"
CORPUS: dict[str, dict[str, object]] = {
    "c_h264_aac_720p.mkv": _clip(
        _V720,
        [440],
        f"-t 8 {_X264} -c:a aac",
        {"video": "h264", "width": 1280, "height": 720, "audio": "aac"},
    ),
    "c_h264_aac_1080p.mov": _clip(
        VIDEO.format(w=1920, h=1080, fps=30),
        [440],
        f"-t 8 {_X264} -c:a aac",
        {"video": "h264", "width": 1920, "height": 1080, "audio": "aac"},
    ),
    "c_h264_aac_1080p60.mp4": _clip(
        VIDEO.format(w=1920, h=1080, fps=60),
        [440],
        f"-t 8 {_X264} -c:a aac -movflags +faststart",
        {"video": "h264", "width": 1920, "height": 1080, "fps": 60, "audio": "aac"},
    ),
    "c_h264_aac_portrait_1080x1920.mp4": _clip(
        VIDEO.format(w=1080, h=1920, fps=30),
        [440],
        f"-t 8 {_X264} -c:a aac",
        {"video": "h264", "width": 1080, "height": 1920, "audio": "aac"},
    ),
    "c_h264_aac_odd_854x480.mp4": _clip(
        VIDEO.format(w=854, h=480, fps=30),
        [440],
        f"-t 8 {_X264} -c:a aac",
        {"video": "h264", "width": 854, "height": 480, "audio": "aac"},
    ),
    "c_h264_ac3_720p.ts": _clip(
        _V720,
        [440],
        f"-t 8 {_X264} -c:a ac3",
        {"video": "h264", "width": 1280, "height": 720, "audio": "ac3"},
    ),
    "c_mpeg4_mp3_480p.avi": _clip(
        VIDEO.format(w=640, h=480, fps=25),
        [440],
        "-t 8 -c:v mpeg4 -vtag xvid -q:v 4 -c:a libmp3lame -b:a 128k",
        {"video": "mpeg4", "width": 640, "height": 480, "audio": "mp3"},
    ),
    "c_mpeg2_mp2_576p.mpg": _clip(
        VIDEO.format(w=720, h=576, fps=25),
        [440],
        "-t 8 -c:v mpeg2video -b:v 5M -c:a mp2 -b:a 192k -f vob",
        {"video": "mpeg2video", "width": 720, "height": 576, "audio": "mp2"},
    ),
    "c_vp8_vorbis_720p.webm": _clip(
        _V720,
        [440],
        "-t 8 -c:v libvpx -deadline realtime -cpu-used 8 -b:v 2M -c:a libvorbis",
        {"video": "vp8", "width": 1280, "height": 720, "audio": "vorbis"},
    ),
    "c_hevc10_aac_1080p.mp4": _clip(
        VIDEO.format(w=1920, h=1080, fps=30),
        [440],
        "-t 8 -c:v libx265 -preset ultrafast -crf 28 -pix_fmt yuv420p10le -tag:v hvc1 "
        "-x265-params log-level=error -c:a aac",
        {"video": "hevc", "width": 1920, "height": 1080, "audio": "aac", "bit_depth": 10},
    ),
    "c_wmv2_wmav2_480p.wmv": _clip(
        VIDEO.format(w=640, h=480, fps=25),
        [440],
        "-t 8 -c:v wmv2 -b:v 2M -c:a wmav2 -b:a 128k",
        {"video": "wmv2", "width": 640, "height": 480, "audio": "wmav2"},
    ),
    "c_theora_vorbis_480p.ogv": _clip(
        VIDEO.format(w=640, h=480, fps=25),
        [440],
        "-t 8 -c:v libtheora -q:v 6 -c:a libvorbis",
        {"video": "theora", "width": 640, "height": 480, "audio": "vorbis"},
    ),
    "c_audio_mp3.mp3": _clip(
        None, [440], "-t 10 -ac 2 -ar 44100 -c:a libmp3lame -b:a 192k", {"audio": "mp3"}
    ),
    "c_audio_flac.flac": _clip(None, [440], "-t 10 -ac 2 -c:a flac", {"audio": "flac"}),
    "c_audio_aac.m4a": _clip(None, [440], "-t 10 -ac 2 -c:a aac -b:a 160k", {"audio": "aac"}),
    "c_audio_pcm.wav": _clip(None, [440], "-t 10 -ac 2 -c:a pcm_s16le", {"audio": "pcm_s16le"}),
    "c_audio_opus.opus": _clip(None, [440], "-t 10 -ac 2 -c:a libopus -b:a 96k", {"audio": "opus"}),
    "c_audio_vorbis.ogg": _clip(None, [440], "-t 10 -ac 2 -c:a libvorbis", {"audio": "vorbis"}),
    "c_audio_ac3_51.ac3": _clip(
        None,
        [440],
        "-t 10 -af aformat=channel_layouts=5.1 -c:a ac3 -b:a 384k",
        {"audio": "ac3", "channels": 6},
    ),
}


# M4 edge-case corpus: unusual but valid media ("valid"), damaged media that must not hang
# or crash the player ("damaged"), and path edge cases. Each recipe is a list of ffmpeg
# argument lists run in order; "{src}" and "{out}" are replaced with real paths.
_E720 = VIDEO.format(w=1280, h=720, fps=30)
EDGE: dict[str, dict[str, object]] = {
    "e_vfr_h264_720p.mkv": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                VIDEO.format(w=1280, h=720, fps=60),
                "-t",
                "8",
                "-vf",
                r"select='lt(mod(n\,10)\,6)'",
                "-fps_mode",
                "vfr",
                *_X264.split(),
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"video": "h264", "width": 1280, "height": 720},
        "why": "variable frame rate (frames dropped in an irregular pattern, original timestamps kept)",
    },
    "e_interlaced_mpeg2_1080i.ts": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                VIDEO.format(w=1920, h=1080, fps=25),
                "-t",
                "6",
                "-c:v",
                "mpeg2video",
                "-vf",
                "setfield=tff",
                "-flags",
                "+ilme+ildct",
                "-field_order",
                "tt",
                "-b:v",
                "8M",
                "-f",
                "mpegts",
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"video": "mpeg2video", "width": 1920, "height": 1080},
        "why": "interlaced (top field first) broadcast-style MPEG-2 in MPEG-TS",
    },
    "e_rotated_90_h264.mp4": {
        "steps": [
            ["-f", "lavfi", "-i", VIDEO.format(w=640, h=360, fps=25), "-t", "6", *_X264.split(), "{src}"],
            ["-display_rotation", "90", "-i", "{src}", "-c", "copy", "{out}"],
        ],
        "kind": "valid",
        "expect": {"video": "h264", "width": 640, "height": 360},
        "why": "display-matrix rotation of 90 degrees stored as metadata (coded size 640x360)",
    },
    "e_hevc10_2160p.mkv": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                VIDEO.format(w=3840, h=2160, fps=30),
                "-t",
                "8",
                "-c:v",
                "libx265",
                "-preset",
                "ultrafast",
                "-crf",
                "30",
                "-pix_fmt",
                "yuv420p10le",
                "-x265-params",
                "log-level=error",
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"video": "hevc", "width": 3840, "height": 2160, "bit_depth": 10},
        "why": "4K HEVC Main 10",
    },
    "e_h264_720p120.mp4": {
        "steps": [
            ["-f", "lavfi", "-i", VIDEO.format(w=1280, h=720, fps=120), "-t", "6", *_X264.split(), "{out}"]
        ],
        "kind": "valid",
        "expect": {"video": "h264", "width": 1280, "height": 720, "fps": 120},
        "why": "high frame rate (120 fps)",
    },
    "e_long_1h_240p.mkv": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                VIDEO.format(w=320, h=240, fps=10),
                "-f",
                "lavfi",
                "-i",
                TONE.format(f=440),
                "-t",
                "3600",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "40",
                "-g",
                "100",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "32k",
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"video": "h264", "width": 320, "height": 240, "duration_s": 3600},
        "why": "one-hour duration (long seeks, h:mm:ss display)",
    },
    "e_mkv_no_cues.mkv": {
        "steps": [["-f", "lavfi", "-i", _E720, "-t", "10", *_X264.split(), "-live", "1", "{out}"]],
        "kind": "valid",
        "expect": {"video": "h264", "width": 1280, "height": 720},
        "why": "Matroska written in live mode: no seek index (cues)",
    },
    "e_fragmented.mp4": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                _E720,
                "-f",
                "lavfi",
                "-i",
                TONE.format(f=440),
                "-t",
                "8",
                *_X264.split(),
                "-c:a",
                "aac",
                "-movflags",
                "frag_keyframe+empty_moov",
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"video": "h264", "width": 1280, "height": 720, "audio": "aac"},
        "why": "fragmented MP4 (empty moov, moof fragments)",
    },
    "e_audio_mono_8k.wav": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=8000,volume=-60dB",
                "-t",
                "8",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"audio": "pcm_s16le", "channels": 1},
        "why": "mono, 8 kHz telephone-quality PCM",
    },
    "e_audio_71_flac.mka": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                TONE.format(f=440),
                "-t",
                "8",
                "-af",
                "aformat=channel_layouts=7.1",
                "-c:a",
                "flac",
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"audio": "flac", "channels": 8},
        "why": "7.1 surround FLAC in Matroska audio",
    },
    "e_audio_96k_24bit.flac": {
        "steps": [
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=96000,volume=-60dB",
                "-t",
                "8",
                "-ac",
                "2",
                "-sample_fmt",
                "s32",
                "-bits_per_raw_sample",
                "24",
                "-c:a",
                "flac",
                "{out}",
            ]
        ],
        "kind": "valid",
        "expect": {"audio": "flac", "channels": 2},
        "why": "high-resolution 96 kHz / 24-bit FLAC",
    },
}

# Copies of a valid clip under awkward names (Unicode, spaces, '#', '%', misleading extension).
PATH_EDGE = {
    "e_ユニコード 名前 — test.mp4": "c_h264_aac_odd_854x480.mp4",
    "e_spaces #hash 100% (x).mp4": "c_h264_aac_odd_854x480.mp4",
    "e_mp4_named.avi": "c_h264_aac_odd_854x480.mp4",
}


# M5 subtitle fixtures. Black video makes rendered text measurable from screen pixels.
# Cues: "FIRST LINE" 1-9 s, "SECOND LINE" 11-19 s (track 2 says "PREMIERE"/"DEUXIEME").
_BLACK = "color=black:size=1280x720:rate=25"
SUB_TEXT = {
    "s_ext.srt": "1\n00:00:01,000 --> 00:00:09,000\nFIRST LINE\n\n2\n00:00:11,000 --> 00:00:19,000\nSECOND LINE\n",
    "s_ext_fra.srt": "1\n00:00:01,000 --> 00:00:09,000\nPREMIERE\n\n2\n00:00:11,000 --> 00:00:19,000\nDEUXIEME\n",
    "s_ext.vtt": "WEBVTT\n\n00:00:01.000 --> 00:00:09.000\nFIRST LINE\n\n00:00:11.000 --> 00:00:19.000\nSECOND LINE\n",
    "s_ext.ass": (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Alignment\n"
        "Style: Default,Arial,48,&H0022C55E,&H00000000,1,2,2\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:09.00,Default,FIRST LINE\n"
        "Dialogue: 0,0:00:11.00,0:00:19.00,Default,SECOND LINE\n"
    ),
    "s_ext.sub": "{25}{225}FIRST LINE\n{275}{475}SECOND LINE\n",
    "s_sidecar_720p.srt": "1\n00:00:01,000 --> 00:00:09,000\nSIDECAR LINE\n",
    "s_ext_unknown_ext.xyz": "1\n00:00:01,000 --> 00:00:09,000\nFIRST LINE\n",
}
SUB_BYTES = {
    "s_ext_cp1252.srt": b"1\r\n00:00:01,000 --> 00:00:09,000\r\nCAF\xc9 R\xc9SUM\xc9 NA\xcfVE\r\n",
    "s_ext_utf8_bom.srt": b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:09,000\nFIRST LINE\n",
    "s_broken.srt": b"this is not\na subtitle file\n\x00\x01\x02 garbage\n",
    "s_empty.srt": b"",
}
SUB_EXPECT = {
    "s_ext.srt": "valid",
    "s_ext_fra.srt": "valid",
    "s_ext.vtt": "valid",
    "s_ext.ass": "valid",
    "s_ext.sub": "valid",
    "s_sidecar_720p.srt": "valid",
    "s_ext_unknown_ext.xyz": "unsupported-extension",
    "s_ext_cp1252.srt": "valid",
    "s_ext_utf8_bom.srt": "valid",
    "s_broken.srt": "unreadable",
    "s_empty.srt": "unreadable",
}


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed ({proc.returncode}): {' '.join(cmd[3:])}\n{proc.stderr[-1500:]}")


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
    for name, spec in {**CLIPS, **CORPUS}.items():
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
                "set": spec["set"],
                "expect": spec["expect"],
                "command": " ".join(Path(c).name if c == ffmpeg else c for c in cmd),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )

    for name, spec in EDGE.items():
        target = OUT / name
        temp = OUT / f"_{Path(name).stem}_src.mp4"
        commands = []
        for step in spec["steps"]:  # type: ignore[attr-defined]
            argv = [str(target) if a == "{out}" else str(temp) if a == "{src}" else a for a in step]
            commands.append([ffmpeg, "-hide_banner", "-y", *argv])
        if args.force or not target.exists():
            print(f"generating {name} ...", flush=True)
            for cmd in commands:
                run(cmd)
            temp.unlink(missing_ok=True)
        entries.append(
            {
                "file": name,
                "kind": spec["kind"],
                "set": "edge",
                "expect": spec["expect"],
                "description": spec["why"],
                "command": " && ".join(
                    " ".join(Path(c).name if c == ffmpeg else c for c in cmd) for cmd in commands
                ),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    for name, source in PATH_EDGE.items():
        shutil.copyfile(OUT / source, OUT / name)
        entries.append(
            {
                "file": name,
                "kind": "valid",
                "set": "edge",
                "expect": next(e["expect"] for e in entries if e["file"] == source),
                "description": f"copy of {source} under an awkward file name",
                "bytes": (OUT / name).stat().st_size,
                "sha256": sha256(OUT / name),
            }
        )
    # Damaged: an MPEG-TS with 64 KiB overwritten (deterministic pattern) at 40 % of the file.
    corrupt = OUT / "e_corrupt_midstream.ts"
    if args.force or not corrupt.exists():
        source_ts = OUT / "_corrupt_source.ts"
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                _E720,
                "-f",
                "lavfi",
                "-i",
                TONE.format(f=440),
                "-t",
                "10",
                *_X264.split(),
                "-c:a",
                "aac",
                "-f",
                "mpegts",
                str(source_ts),
            ]
        )
        data = bytearray(source_ts.read_bytes())
        start = int(len(data) * 0.4)
        data[start : start + 65536] = bytes((i * 151 + 17) % 256 for i in range(65536))
        corrupt.write_bytes(bytes(data))
        source_ts.unlink()
    (OUT / "e_empty.mp4").write_bytes(b"")
    for name, kind, why in [
        (
            "e_corrupt_midstream.ts",
            "damaged",
            "64 KiB of the stream overwritten at 40 %; must not hang or crash",
        ),
        ("e_empty.mp4", "invalid", "zero-byte file"),
    ]:
        entries.append(
            {
                "file": name,
                "kind": kind,
                "set": "edge",
                "expect": {"opens": False} if kind == "invalid" else {"survives": True},
                "description": why,
                "bytes": (OUT / name).stat().st_size,
                "sha256": sha256(OUT / name),
            }
        )

    # M5 subtitle fixtures: text files first (they are muxed into the MKV below).
    for name, text in SUB_TEXT.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    for name, data in SUB_BYTES.items():
        (OUT / name).write_bytes(data)
    sub_videos = {
        "s_black_tracks_720p.mkv": (
            [
                "-f",
                "lavfi",
                "-i",
                _BLACK,
                "-f",
                "lavfi",
                "-i",
                TONE.format(f=440),
                "-f",
                "lavfi",
                "-i",
                TONE.format(f=880),
                "-i",
                str(OUT / "s_ext.srt"),
                "-i",
                str(OUT / "s_ext_fra.srt"),
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
                *_X264.split(),
                "-c:a",
                "aac",
                "-c:s",
                "srt",
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
                "-disposition:s:0",
                "0",
                "-disposition:s:1",
                "0",
            ],
            {"video": "h264", "width": 1280, "height": 720, "audio_tracks": 2, "subtitle_tracks": 2},
            "black video, 2 audio (eng/fra) + 2 embedded SRT (eng/fra) tracks, no default flags",
        ),
        "s_black_720p.mp4": (
            [
                "-f",
                "lavfi",
                "-i",
                _BLACK,
                "-f",
                "lavfi",
                "-i",
                TONE.format(f=440),
                "-t",
                "20",
                *_X264.split(),
                "-c:a",
                "aac",
            ],
            {"video": "h264", "width": 1280, "height": 720, "audio": "aac"},
            "black video, no subtitles (external subtitle tests)",
        ),
        "s_sidecar_720p.mp4": (
            ["-f", "lavfi", "-i", _BLACK, "-t", "10", *_X264.split()],
            {"video": "h264", "width": 1280, "height": 720},
            "black video with a same-name .srt next to it (auto-load test)",
        ),
    }
    for name, (argv, expect, why) in sub_videos.items():
        target = OUT / name
        cmd = [ffmpeg, "-hide_banner", "-y", *argv, str(target)]
        if args.force or not target.exists():
            print(f"generating {name} ...", flush=True)
            run(cmd)
        entries.append(
            {
                "file": name,
                "kind": "valid",
                "set": "subtitles",
                "expect": expect,
                "description": why,
                "command": " ".join(Path(c).name if c == ffmpeg else c for c in cmd),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    for name, expectation in SUB_EXPECT.items():
        path = OUT / name
        entries.append(
            {
                "file": name,
                "kind": "subtitle",
                "set": "subtitles",
                "expect": {"subtitle": expectation},
                "description": "external subtitle file",
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
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
