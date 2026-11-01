"""libVLC plugin audit and curation (M10).

Every libVLC 3 plugin exports ``vlc_entry_license__3_0_0f`` and ``vlc_entry_copyright__3_0_0f``,
which return its licence and copyright strings. This tool reads them without running any
plugin code (the DLL is mapped with DONT_RESOLVE_DLL_REFERENCES: no imports, no DllMain), and
decides which plugins the release ships:

* EXCLUDED_DIRS / EXCLUDED: capture devices, disc access (DVD/Blu-ray CSS/AACS concerns, M1),
  conditional access, network protocols Babarify does not offer, control interfaces, Lua,
  service discovery, renderers (Chromecast), visualisations and encoders it does not use.
* Everything else (demuxers, decoders, audio/video output, filters, packetizers, the http and
  rtsp access the proxy and RTSP need, and the stream output used by the AI worker) is kept.

Usage:
  python tools/vlc_plugins.py audit  [vlc_dir] [out.json]   list every plugin and its licence
  python tools/vlc_plugins.py curate [vlc_dir] <target_dir>  copy the kept set + rebuild cache
"""

from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VLC = ROOT / ".engines" / "vlc" / "vlc-3.0.24"
DONT_RESOLVE_DLL_REFERENCES = 0x00000001

# Whole plugin folders the release does not need.
EXCLUDED_DIRS = {
    "control": "remote-control interfaces (http, telnet, hotkeys...): not used by an embedded player",
    "gui": "VLC's own interfaces",
    "lua": "Lua scripting: disabled with --no-lua (M8)",
    "services_discovery": "network/device discovery (UPnP, SAP, mDNS...)",
    "visualization": "audio visualisations: not offered",
    "keystore": "credential stores: Babarify stores no passwords",
    "logger": "file/syslog loggers: the app keeps its own log",
    "meta_engine": "online cover-art and lyrics fetchers",
    "stream_extractor": "archive extraction",
    "spu": "",  # placeholder; real entries below decide per plugin
}
EXCLUDED_DIRS.pop("spu")
# Individual plugins (file name) the release does not ship, and why.
EXCLUDED = {
    # Capture devices and screen: never reachable, removed as defence in depth (M8 note).
    "libdshow_plugin.dll": "camera/microphone capture",
    "libscreen_plugin.dll": "screen capture",
    "libaccess_wasapi_plugin.dll": "audio capture",
    "libdtv_plugin.dll": "TV tuner capture",
    "libdcp_plugin.dll": "digital cinema packages",
    "libvdr_plugin.dll": "VDR recordings",
    "libshm_plugin.dll": "shared-memory capture",
    "libimem_plugin.dll": "in-memory input (not used)",
    "libaccess_imem_plugin.dll": "in-memory input (not used)",
    "libidummy_plugin.dll": "vlc:// control URLs",
    "libtimecode_plugin.dll": "test-pattern input",
    # Disc access: CSS/AACS circumvention concerns (M1 licensing report).
    "libdvdnav_plugin.dll": "DVD access (libdvdcss)",
    "libdvdread_plugin.dll": "DVD access (libdvdcss)",
    "liblibbluray_plugin.dll": "Blu-ray access",
    "libcdda_plugin.dll": "audio CD access",
    "libvcd_plugin.dll": "VCD access",
    "libaribcam_plugin.dll": "ARIB conditional access",
    # Network protocols Babarify does not offer (http/https/rtsp only, M8).
    "libftp_plugin.dll": "ftp", "libsftp_plugin.dll": "sftp", "libsmb_plugin.dll": "smb",
    "libnfs_plugin.dll": "nfs", "libaccess_mms_plugin.dll": "mms", "libvnc_plugin.dll": "vnc",
    "libaccess_srt_plugin.dll": "srt", "librist_plugin.dll": "rist", "libsatip_plugin.dll": "SAT>IP",
    "libudp_plugin.dll": "udp", "librtp_plugin.dll": "rtp", "libtcp_plugin.dll": "raw tcp",
    "libaccess_concat_plugin.dll": "concatenated inputs",
    "libsdp_plugin.dll": "SDP sessions",
    # Renderers and network outputs.
    "libdemux_chromecast_plugin.dll": "Chromecast",
    "libstream_out_chromecast_plugin.dll": "Chromecast",
    "libaccess_output_http_plugin.dll": "streaming server",
    "libaccess_output_livehttp_plugin.dll": "streaming server",
    "libaccess_output_shout_plugin.dll": "streaming server",
    "libaccess_output_srt_plugin.dll": "streaming server",
    "libaccess_output_udp_plugin.dll": "streaming server",
    "libaccess_output_rist_plugin.dll": "streaming server",
    "libstream_out_rtp_plugin.dll": "streaming server",
    # Online services and servers: privacy-first player (M10 review).
    "libaudioscrobbler_plugin.dll": "submits listening history to Last.fm",
    "libfingerprinter_plugin.dll": "online AcoustID lookups",
    "libaddonsvorepository_plugin.dll": "downloads VLC add-ons",
    "libaddonsfsstorage_plugin.dll": "VLC add-on storage",
    "libvod_rtsp_plugin.dll": "RTSP streaming server",
    "libexport_plugin.dll": "playlist export (not used)",
    "liblogger_plugin.dll": "file logger (the app keeps its own log)",
    "libhds_plugin.dll": "Adobe HDS: would fetch segments around the stream proxy (M8)",
    "libstream_out_smem_plugin.dll": "not used",
    # Video encoders (the AI worker only writes 16-bit PCM WAV).
    "libx264_plugin.dll": "H.264 encoder", "libx26410b_plugin.dll": "H.264 encoder",
    "libx265_plugin.dll": "HEVC encoder", "libtheora_plugin.dll": "",  # decoder too: kept
}  # fmt: skip
EXCLUDED.pop("libtheora_plugin.dll")
# Stream output and muxers: the AI worker needs only #transcode + #std into a WAV file.
KEEP_ONLY = {
    "stream_out": {"libstream_out_transcode_plugin.dll", "libstream_out_standard_plugin.dll",
                   "libstream_out_dummy_plugin.dll"},
    "mux": {"libmux_wav_plugin.dll", "libmux_dummy_plugin.dll"},
}  # fmt: skip


def _symbol(dll: ctypes.CDLL, name: str) -> str:
    try:
        fn = getattr(dll, name)
    except AttributeError:
        return ""
    fn.restype = ctypes.c_char_p
    value = fn()
    return value.decode("utf-8", "replace") if value else ""


def audit(vlc_dir: Path) -> list[dict[str, str]]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LoadLibraryExW.restype = ctypes.c_void_p
    kernel32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
    rows = []
    for dll_path in sorted((vlc_dir / "plugins").rglob("*.dll")):
        handle = kernel32.LoadLibraryExW(str(dll_path), None, DONT_RESOLVE_DLL_REFERENCES)
        licence = copyright_ = ""
        if handle:
            dll = ctypes.CDLL(str(dll_path), handle=handle)
            licence = _symbol(dll, "vlc_entry_license__3_0_0f")
            copyright_ = _symbol(dll, "vlc_entry_copyright__3_0_0f")
            kernel32.FreeLibrary(handle)
        folder = dll_path.parent.name
        reason = EXCLUDED.get(dll_path.name) or EXCLUDED_DIRS.get(folder, "")
        if not reason and folder in KEEP_ONLY and dll_path.name not in KEEP_ONLY[folder]:
            reason = "stream output not used (only transcode to WAV for the AI worker)"
        rows.append({
            "plugin": dll_path.name, "folder": folder, "licence": licence or "unknown",
            "copyright": copyright_, "shipped": "no" if reason else "yes", "reason": reason,
        })  # fmt: skip
    return rows


def curate(vlc_dir: Path, target: Path) -> list[dict[str, str]]:
    rows = audit(vlc_dir)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for item in vlc_dir.iterdir():  # the two core DLLs and the licence/credit texts only
        if item.is_file() and (
            item.name in {"libvlc.dll", "libvlccore.dll"} or item.suffix.lower() == ".txt"
        ):
            shutil.copy2(item, target / item.name)
    for row in rows:
        if row["shipped"] == "yes":
            dest = target / "plugins" / row["folder"] / row["plugin"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(vlc_dir / "plugins" / row["folder"] / row["plugin"], dest)
    # A plugin cache for exactly this set (faster start; libVLC rebuilds it if missing).
    cache_gen = vlc_dir / "vlc-cache-gen.exe"
    if cache_gen.exists():
        subprocess.run([str(cache_gen), str(target / "plugins")], check=True, capture_output=True)
    (target / "plugins.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("audit", "curate"):
        print(__doc__)
        return 2
    vlc_dir = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "audit" else DEFAULT_VLC
    if sys.argv[1] == "audit":
        rows = audit(vlc_dir)
        out = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    else:
        if len(sys.argv) > 3:
            vlc_dir, target = Path(sys.argv[2]), Path(sys.argv[3])
        else:
            target = Path(sys.argv[2])
        rows = curate(vlc_dir, target)
        out = None
    by_licence: dict[str, list[int]] = {}
    for row in rows:
        counts = by_licence.setdefault(row["licence"], [0, 0])
        counts[0 if row["shipped"] == "yes" else 1] += 1
    for licence, (shipped, dropped) in sorted(by_licence.items(), key=lambda kv: -sum(kv[1])):
        print(f"{licence:30} shipped {shipped:3}  excluded {dropped:3}")
    print(f"total {len(rows)}: shipped {sum(r['shipped'] == 'yes' for r in rows)}")
    if out is not None:
        out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
