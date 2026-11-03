"""Generate the prototype's small synthetic test clips into media/ (requires ffmpeg)."""

from __future__ import annotations

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEDIA = HERE / "media"
SECONDS = "12"
VIDEO = f"testsrc2=size=320x180:rate=15:duration={SECONDS}"
AUDIO = f"sine=frequency=440:duration={SECONDS}"

CLIPS: dict[str, list[str]] = {
    "h264_aac.mp4": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
    "h264_aac.mkv": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
    "h264_ac3.ts": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "ac3"],
    "hevc8_aac.mp4": ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-c:a", "aac"],
    "hevc10_aac.mp4": ["-c:v", "libx265", "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1", "-c:a", "aac"],
    "vp9_opus.webm": ["-c:v", "libvpx-vp9", "-c:a", "libopus"],
    "vp8_vorbis.webm": ["-c:v", "libvpx", "-c:a", "libvorbis"],
    "av1_opus.mkv": ["-c:v", "libaom-av1", "-cpu-used", "8", "-c:a", "libopus"],
    "mpeg2_mp2.mpg": ["-c:v", "mpeg2video", "-c:a", "mp2"],
    "mpeg4_mp3.avi": ["-c:v", "mpeg4", "-c:a", "libmp3lame"],
    "wmv2_wma.wmv": ["-c:v", "wmv2", "-c:a", "wmav2"],
    "theora_vorbis.ogv": ["-c:v", "libtheora", "-c:a", "libvorbis"],
}
AUDIO_CLIPS: dict[str, list[str]] = {
    "audio_aac.m4a": ["-c:a", "aac"],
    "audio_mp3.mp3": ["-c:a", "libmp3lame"],
    "audio_flac.flac": ["-c:a", "flac"],
    "audio_opus.opus": ["-c:a", "libopus"],
    "audio_vorbis.ogg": ["-c:a", "libvorbis"],
    "audio_ac3.ac3": ["-c:a", "ac3"],
    "audio_pcm.wav": ["-c:a", "pcm_s16le"],
}
SUBTITLES = "1\n00:00:00,500 --> 00:00:11,000\nFIRST LINE\n"


def ffmpeg(*arguments: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *arguments], check=True)


def main() -> None:
    MEDIA.mkdir(exist_ok=True)
    for name, options in CLIPS.items():
        ffmpeg("-f", "lavfi", "-i", VIDEO, "-f", "lavfi", "-i", AUDIO, *options, str(MEDIA / name))
    for name, options in AUDIO_CLIPS.items():
        ffmpeg("-f", "lavfi", "-i", AUDIO, *options, str(MEDIA / name))

    # A long clip for seek, rotation and leave-and-return runs.
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=60",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
        "-c:v", "libx264", "-crf", "38", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "16k",
        "-movflags", "+faststart", str(MEDIA / "long_60s.mp4"),
    )  # fmt: skip

    (MEDIA / "subs.srt").write_text(SUBTITLES, "utf-8")
    ffmpeg(
        "-f", "lavfi", "-i", VIDEO,
        "-f", "lavfi", "-i", AUDIO,
        "-f", "lavfi", "-i", "sine=frequency=880:duration=" + SECONDS,
        "-i", str(MEDIA / "subs.srt"),
        "-map", "0", "-map", "1", "-map", "2", "-map", "3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "srt",
        "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=fra",
        str(MEDIA / "multitrack.mkv"),
    )  # fmt: skip

    (MEDIA / "not_media.mp4").write_text("this is not a media file\n", "utf-8")
    (MEDIA / "empty.mp4").write_bytes(b"")
    whole = (MEDIA / "h264_aac.mp4").read_bytes()
    (MEDIA / "truncated.mp4").write_bytes(whole[: len(whole) // 3])


if __name__ == "__main__":
    main()
