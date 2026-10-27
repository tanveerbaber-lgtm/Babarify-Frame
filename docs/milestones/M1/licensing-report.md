# M1 Preliminary Licensing and Distribution Report

**Status:** preliminary engineering inventory. **This is not legal advice and not a
legal clearance.** Items marked *Legal review* need a qualified reviewer before any
public binary is distributed. No installer or binary has been published.

Legend: **Verified** = checked against the actual files/metadata in this environment.
**Assumption** = based on general project knowledge, not yet checked against source.
**Open** = unresolved question.

## 1. Babarify Frame's own code

| Item | Status |
|---|---|
| Project license | **Open — decided by the owner: "decide later".** No `LICENSE` file; all rights reserved by default. The README states this. |
| Constraint | If the shipped engine build is GPL (both candidate builds evaluated here are, see §3), distributing the app *together with* it means the combined work must be distributable under the GPL. A permissive license for Babarify's own code remains possible (it is GPL-compatible), but the distributed bundle carries GPL obligations. **Legal review.** |
| Name/trademark | "Babarify Frame" — no trademark search done. **Open** (plan §2.1). Do not use "VLC", "VideoLAN" or the VLC cone in branding (VideoLAN trademarks). **Assumption.** |

## 2. Runtime Python dependencies (would be distributed)

Verified with `pip-licenses 5.5.5` against the installed packages.

| Package | Version | License (from package metadata) | Distributed? | Obligations / notes |
|---|---|---|---|---|
| PySide6-Essentials, shiboken6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | Yes | Choose LGPL-3.0 route: ship license texts, allow users to replace the Qt/PySide libraries (keep them as separate DLLs, don't statically link), provide or point to source of the exact Qt version. Qt's own modules have per-module licenses: only use LGPL-available modules. **Verified (metadata)**, module-level check **Open** |
| PySide6-Addons, Pdf, WebEngine | 6.12.0 | same | **No** — dev convenience only; must be excluded from packaging (WebEngine also bundles Chromium with many more licenses) | M10 packaging must exclude |
| python-vlc | 3.0.21203 | LGPL-2.1-or-later | If libVLC is chosen | Notice + license text. **Verified (metadata)** |
| mpv (python-mpv) | 1.0.8 | GPL-2.0-or-later; LGPL-2.1-or-later (package metadata lists both) | If mpv is chosen | Which applies depends on the libmpv build being linked. **Verified (metadata)** |

Development-only (not distributed): pytest, pytest-qt, ruff, mypy, psutil, pip-licenses
and their dependencies (MIT / BSD / Apache-2.0 / MPL-2.0 / PSF-2.0). psutil (BSD-3-Clause)
is only used by the benchmark. FFmpeg 9.0.2 (gyan.dev GPL build) is a dev tool used to
generate test media and is never distributed.

## 3. Playback engines

### 3.1 libVLC — `vlc-3.0.24-win64.zip` (VideoLAN official build)

| Finding | Status |
|---|---|
| Top-level `COPYING.txt` in the zip is **GPL-2.0**. | **Verified** |
| libVLC core (`libvlc.dll`, `libvlccore.dll`) is LGPL-2.1-or-later in VLC 3.x. | **Assumption** (VideoLAN relicensed the core in 2011–2012); confirm against VLC 3.0.24 source headers |
| The zip contains **360 plugin DLLs**. Many plugins and their bundled third-party libraries are **GPL** (e.g. x264/x265 encoders `libx264_plugin.dll`, `libx265_plugin.dll`; `libpostproc_plugin.dll`; `libfaad_plugin.dll`; `libmad_plugin.dll`; DVD access). Shipping these makes the distributed bundle subject to the GPL (source offer for the exact build). | Plugin presence **Verified**; per-plugin licenses **Open** |
| `libdvdread_plugin.dll` and `libdvdnav_plugin.dll` contain **libdvdcss** references (DVD CSS decryption). Distributing CSS circumvention code is legally restricted in some jurisdictions (e.g. US DMCA §1201, EU Copyright Directive art. 6). | Strings **Verified**; legal effect **Legal review**. **Recommendation: exclude DVD/Blu-ray access plugins from any Babarify build.** |
| `libaribcam_plugin.dll` (ARIB conditional-access) — similar circumvention concern. | Presence **Verified**; **Legal review**; recommend exclude |
| Network/streaming plugins (http(s), ftp, sftp, smb, nfs, upnp, chromecast, srt, stream_out/*, Lua extension scripts). Not a license issue but a **security/attack-surface** issue before M8. | **Verified** presence; recommend exclude until M8 |
| A production build should use a **custom plugin set** (only demuxers/decoders/outputs needed for local playback), with a generated notice file listing every shipped plugin and its license. | Recommendation |

### 3.2 libmpv — shinchiro `mpv-dev-x86_64-20261021-git-e471496c56`

| Finding | Status |
|---|---|
| mpv is GPL-2.0-or-later by default; an LGPL-2.1-or-later build is possible with `-Dgpl=false`, which drops some features. | **Assumption** (mpv documentation); |
| This build's `mpv-configuration` property (queried with `tools/engine-benchmark/engine_build_info.py`) has **no `-Dgpl=false`**, so it is the default **GPL** build. It also enables `dvdnav`, `libbluray`, `libcurl` (network), `lua`, `javascript`, `vapoursynth`, `rubberband` (GPL), `libarchive`, `vulkan`, `spirv-cross`, `pdf-build`. DVD/Blu-ray access raises the same circumvention question as libVLC's DVD plugins (whether libdvdcss/AACS code is linked in is **Open**). | Configuration **Verified**; component licenses **Open** |
| libVLC reports `3.0.24 Vetinari`, changeset `3.0.24-rc1-0-g6de05adcba`, built with GCC 6.4.0. | **Verified** |
| `libmpv-2.dll` (121 MB) is a **single statically linked DLL** containing FFmpeg, libplacebo, libass, dav1d and many other libraries. Their licenses and the FFmpeg configure flags cannot be listed from the binary alone; a distributable build needs either the builder's full configuration/source record or a **self-built** libmpv with a known dependency list. | Static linking **Verified** (single DLL, no separate FFmpeg DLLs); dependency licenses **Open** |
| The build is from a third-party builder (linked from mpv.io), not from the mpv project. Provenance for redistribution: **Open** — prefer a reproducible in-house build for M10. | |

### 3.3 FFmpeg (inside both engines)

Both engines embed FFmpeg (VLC via `libavcodec_plugin.dll` etc.; mpv statically). FFmpeg
is LGPL-2.1+ unless built with `--enable-gpl` / `--enable-nonfree`. A `nonfree` build is
**not redistributable**. The configure flags of both bundled FFmpegs are **Open**; a
release build must document them (see https://ffmpeg.org/legal.html).

## 4. Codec patents (both engines)

Software decoders for H.264/AVC, HEVC/H.265, AAC, AC-3/E-AC-3, and others are covered
by patent pools in some territories (e.g. Via LA, Access Advance, Avanci Video). Being
free does not remove patent exposure. AV1, VP9 and Opus are designed as royalty-free.
Hardware decoding through the GPU/OS (D3D11VA, observed in M1) may reduce but does not
remove exposure, because software fallbacks still ship. **Legal review** for each
target territory before public release.

## 5. Obligations checklist for a future release (M10)

1. Choose the project license (owner decision).
2. Select the engine (ADR-0001) and produce a **known, reproducible engine build**
   with a recorded configuration (plugin list or meson options, FFmpeg flags).
3. Exclude DVD/Blu-ray/CAS circumvention components and pre-M8 network modules.
4. Generate `THIRD_PARTY_NOTICES.md` from the actual shipped files (engine + plugins +
   Qt/PySide modules + Python packages), with license texts.
5. Provide a written source offer or source archive for all GPL/LGPL components at
   the exact versions shipped; keep LGPL libraries dynamically linked and replaceable.
6. Exclude PySide6-Addons/WebEngine/Pdf unless a feature needs them.
7. Trademark search for "Babarify Frame"; avoid VideoLAN/mpv marks in branding.
8. Patent review per territory.

## 6. Unresolved questions (owner / legal reviewer)

| # | Question | Owner |
|---|---|---|
| L1 | License for Babarify Frame's own code | Tanveer Baber |
| L2 | Accept GPL obligations for distributed engine bundle, or pursue an LGPL-only engine build (feature trade-offs) | Tanveer Baber + legal review |
| L3 | Patent exposure for H.264/HEVC/AAC/AC-3 decoding in target countries | Legal review |
| L4 | Trademark clearance for "Babarify Frame" | Tanveer Baber |
| L5 | Build provenance: self-build the selected engine for release? | Engineering (M2/M10) |
