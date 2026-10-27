"""Print build/version information reported by the engines themselves (evidence for the licensing report).

Usage:  python tools/engine-benchmark/engine_build_info.py
"""

from __future__ import annotations

from babarify_frame.playback.adapters.libvlc import _load_vlc
from babarify_frame.playback.adapters.mpv import _load_mpv


def main() -> None:
    vlc = _load_vlc()
    print("libvlc version :", vlc.libvlc_get_version().decode())
    print("libvlc compiler:", vlc.libvlc_get_compiler().decode())
    print("libvlc changeset:", vlc.libvlc_get_changeset().decode())

    mpv = _load_mpv()
    player = mpv.MPV(vo="null", ao="null", config=False, load_scripts=False, ytdl=False)
    try:
        for prop in ("mpv-version", "ffmpeg-version", "libass-version", "mpv-configuration"):
            try:
                print(f"mpv {prop}:", player._get_property(prop))
            except Exception as exc:
                print(f"mpv {prop}: <unavailable: {exc}>")
    finally:
        player.terminate()


if __name__ == "__main__":
    main()
