# M8 Acceptance Report — Advanced Media and Network Features

**Date:** 2026-11-01 · **Engine:** libVLC 3.0.24 x64 (mpv: local files only) ·
**Machine:** i7-8565U, Intel UHD 620, Windows 11, 3840×2160 @ 250 % ·
**Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **PASS** — accepted by the owner on 2026-11-01

Scope chosen by the owner: the "core four". These are network streams, chapters and
bookmarks, seek-bar previews, and detailed media information. Excluded: 360°/stereoscopic
playback and conversion/capture (§4).

All five acceptance criteria have recorded evidence. The main finding came from the spike.
Plain libVLC followed an HTTP redirect to `file:///…` and played the local file (R34). The
same applies to HLS manifests that name `file:` segments, and libVLC has no option to
prevent it. Babarify therefore never lets libVLC fetch a web address. A loopback proxy owned
by the app does all HTTP(S) fetching, follows redirects only to web addresses, and rewrites
playlists so every entry passes through it again. Real-libVLC tests show that a redirect to a
local file, an HLS segment pointing at a local file, and playlist entries such as `vlc://quit`
are all refused or skipped, and nothing local is played.

## Acceptance criteria (plan §8, M8)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Each feature has independent tests and documented capability requirements | **PASS** | Network: `tests/unit/test_network.py` (address rules), `tests/unit/test_stream_proxy.py` (proxy over real sockets), `tests/integration/test_network_engine.py` (real libVLC with a local server). Chapters, bookmarks, information and previews: `tests/ui/test_advanced_media_ui.py`, bookmark tests in `tests/unit/test_library_db.py`, and real-libVLC chapter, tag and preview tests. Capabilities: `EngineCapabilities.network_schemes` and `supports_chapters`. The preview contract is `FramePreview`. Each is documented in the [architecture overview](../../architecture/overview.md#network-streams-m8). |
| A2 | Network inputs are treated as untrusted | **PASS** | Every address goes through `validate_stream_url`: typed, dropped, from history, or from inside a playlist. It allows http/https/rtsp only, requires a host, refuses credentials, whitespace and control characters, caps length at 2,048 characters and drops the fragment (21 refusal cases tested). Server responses are untrusted too. Playlists are size-capped (4 MB) and rewritten. DASH/Smooth XML is refused. Tags and track titles are HTML-escaped and shortened in the media panel (`test_untrusted_tags_are_escaped_and_shortened`). Query strings (often access tokens) never appear in titles, the recent-streams list or the media panel. |
| A3 | No arbitrary command execution through media URLs or playlists | **PASS** | Engine-control and device schemes are refused at the contract: `vlc://`, `dshow://`, `screen://`, `smb://`, `file:` as a stream. They are also refused as redirect targets (proxy, 502) and as playlist entries (skipped with a notice). libVLC runs with `--no-lua`, so no Lua playlist or meta scripts run on downloaded content. The proxy listens on 127.0.0.1 only and needs a random per-process token (403 without it). R34 tests: `test_redirect_to_a_local_file_is_refused`, `test_hls_with_a_local_file_segment_is_refused`, `test_playlist_skips_local_and_vlc_entries`. |
| A4 | Unsupported protocols and media are handled safely | **PASS** | Each case fails with `NETWORK_ERROR` and a reason, and nothing plays (position 0): 404 ("the server answered 404 …"), non-media ("did not return playable media"), DASH ("not supported"), unknown host, closed port, rtsp refusal. All take under 10 s. A server that accepts the connection and never answers would leave libVLC opening forever; the adapter gives up after 30 s (tested at 3 s), and the engine plays the next file normally. Unsupported schemes are refused before anything is fetched, and the dialog explains why while you type. An engine without network support (mpv) disables the dialog with an explanation. |
| A5 | Optional modules do not destabilise local playback | **PASS** | Previews use a second, muted, windowless player on the probe's shared instance; main playback keeps advancing while previews decode (`test_previews_are_real_frames_and_do_not_disturb_playback`). Previews run on one background thread, decode only the newest request, and can be turned off in Settings. Local playback works after network failures (`test_local_playback_still_works_after_streams`). Full suite: see §1. |

### Deliverables

| Deliverable | Status |
|---|---|
| Chapter navigation and timeline bookmarks | ✅ Chapters from the file: *Playback → Chapters* menu, **Ctrl+→ / Ctrl+←** (previous restarts the current chapter after 3 s), grey marks on the seek bar, chapter name in the hover popup. Bookmarks: **Ctrl+B** adds, **Ctrl+Shift+B** lists (go to, rename, delete); amber marks; stored locally per file (library schema v3), kept when history is cleared |
| Seek-bar thumbnail previews | ✅ Local video files: a picture, the time and the chapter above the seek bar; time and chapter only for audio and streams |
| Detailed media information | ✅ **Ctrl+Shift+I**: file, size, overall bitrate, container, duration, tags, every track (codec, size, frame rate, channels, sample rate, language), chapters; Copy |
| 360° and stereoscopic | ❌ Not built (§4) |
| Network streams and supported sources | ✅ **Ctrl+N** or a dropped link: http/https files with seeking, HLS, M3U/PLS/XSPF lists, internet radio, rtsp |
| Conversion or capture | ❌ Not built (§4) |

## 1. Test results

| Suite | Result |
|---|---|
| Address rules: `tests/unit/test_network.py` | 32 passed |
| Stream proxy (real sockets, no libVLC): `tests/unit/test_stream_proxy.py` | 17 passed |
| Bookmarks and schema v3: `tests/unit/test_library_db.py` | 33 passed (3 new) |
| UI with the mock engine: `tests/ui/test_advanced_media_ui.py` | 13 passed |
| Real libVLC with a local server: `tests/integration/test_network_engine.py` | 13 passed |
| Full default suite | **524 passed**, 0 failed (445 before M8); final run after the evidence fixes: §1.1 |
| ruff and strict mypy | clean |

### 1.1 Final run

After the R38/R39 fixes and the evidence retake: ruff (check and format) clean, strict mypy clean,
full default suite **524 passed**, 72 skipped (mpv opt-in and missing optional media), 0 failed,
no crash (run with `-X faulthandler`).

## 2. Measurements (`tools/m8_measure.py`, JSON in `tools/engine-benchmark/results/m8_measure.json`)

Seek previews: 20 random times per file, after opening.

| File | Open | Median | Worst | No picture |
|---|---|---|---|---|
| H.264 1080p30 | 878 ms | 129 ms | 355 ms | 0 / 20 |
| HEVC 2160p30 | 371 ms | 688 ms | 1,187 ms | 0 / 20 |
| AV1 1080p30 | 807 ms | 64 ms | 383 ms | **5 / 20** |
| H.264 240p, 1 hour | 659 ms | 10 ms | 115 ms | 0 / 20 |

Stream proxy: a 33 MB file read from a 127.0.0.1 server took 412 MB/s through the proxy and
910 MB/s directly, with identical bytes. That is far more than any stream needs (a 4K stream
is about 3 MB/s).

## 3. Limitations

1. **RTSP is not proxied.** libVLC's RTSP client (live555) only speaks RTSP/RTP and does not
   hand redirects to other access modules. The proxy's guarantee covers http/https only.
2. **DASH and Smooth Streaming are refused.** The proxy does not rewrite their XML manifests,
   and passing them through would let libVLC fetch segments itself. HLS is supported.
3. **mpv** (alternate engine) plays local files only; its network schemes are empty, and the
   dialog says so.
4. **Previews:** local video files only (a stream would be downloaded twice). On AV1, 5 of 20
   seeks gave no picture within the 2 s limit; the popup then shows time and chapter only.
   4K previews take about 0.7 s. The size includes libVLC's decoder padding (under 1 %).
5. **Live streams** have no duration, so seeking, bookmarks and A-B repeat are off for them.
6. **History** stores a stream's full address, including any query string, so it can be
   reopened. Titles and lists never show the query. The address stays on this PC, and
   history can be switched off or cleared.
7. **Media information** shows what libVLC reports. Per-track bitrate is usually not
   reported. Tag mapping follows libVLC; for example, an MKV "artist" tag appears as
   *Album artist*.
8. **Redirect limit:** at most 5 redirects; certificate errors are refused (no override).
9. **Packaging (M10 note):** the bundled libVLC plugins include capture modules (dshow,
   screen). They are unreachable from Babarify (schemes refused, no libVLC web fetching), but
   M10 should ship a reduced plugin set as defence in depth.

## 4. Not built, and why

- **360° and stereoscopic playback:** few users, and a proper control (drag to look, field
  of view) needs viewpoint-API work and test media that M8 did not justify. The plan says
  "if technically justified"; it can be revisited.
- **Conversion and capture:** the plan requires a licensing and security review first.
  Capture (screen, camera) runs against M8's own rule of keeping device access unreachable.

## 5. Defects found and fixed

| ID | Defect | Fix |
|---|---|---|
| R34 | A web server could make the player open a local file (redirect or HLS segment) | Loopback proxy does all web fetching; `--no-lua` |
| R35 | Remote plain M3U with a valid entry failed | Plain M3U served as `audio/x-mpegurl`, not HLS |
| R36 | First seek-bar hover sometimes got no picture | Requests queue as soon as a file is set |
| R37 | Long bookmark names kept a trailing space | Strip after cutting |
| R38 | Media information drawn white with nearly invisible text | Theme styles text views |
| R39 | Long error reasons lost their last line | Message body at least 480 px wide |

R38 and R39 were found by inspecting the evidence screenshots, which were retaken after
the fixes.

## 6. Changes

- Core: `core/network.py` (address rules), `ErrorCode.NETWORK_ERROR`, `Chapter`,
  `MediaInfo.chapters/metadata`, track details, `network_schemes`, `supports_chapters`.
- Playback: `playback/stream_proxy.py`; `playback/preview.py` and
  `adapters/libvlc_preview.py`; libVLC adapter: proxy, open timeout, playlist entries,
  chapters (ctypes), tags, track details, `--no-lua`; mock: chapters and simulated streams.
- Library: schema v3 `bookmarks`.
- UI: `ui/network.py` (Ctrl+N), `ui/media_info.py` (Ctrl+Shift+I), `ui/bookmarks.py`,
  `ui/seek_preview.py`, seek-bar marks and hover, chapter and bookmark actions, the
  *Settings → Playback* preview switch, dropped links.
- Tools: `advanced_media_screenshot.py`, `m8_measure.py`; test helper `tests/netserver.py`.
- Evidence ([`evidence/`](evidence/)): `seek_preview.png` (picture, time and chapter above
  the bar; chapter and bookmark marks), `media_info.png`, `bookmarks.png`,
  `stream_dialog_refused.png`, `stream_dialog_ok.png`, `redirect_refused.png`. All inspected.
