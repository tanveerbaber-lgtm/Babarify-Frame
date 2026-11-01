# M10 Acceptance Report — Windows Packaging, Security, and Release

**Date:** 2026-11-01 · **Version:** 0.9.0 (release candidate for the M11 beta) ·
**Machine:** i7-8565U, Windows 11 Home 10.0.26300 · **Tools:** PyInstaller 6.22.3,
Inno Setup 6.7.4 (Authenticode-verified download) · **Prepared by:** Claude (Claude Code) ·
**Decision owner:** Tanveer Baber

## Decision: **PASS** — accepted by the owner on 2026-11-01

Owner decisions:
- **Licence:** GPL-3.0-or-later.
- **Installer:** PyInstaller and Inno Setup.
- **Signing:** none for now, ship unsigned.

All seven acceptance criteria have evidence from `tools/release_check.py`, which installs,
runs, upgrades, rolls back and uninstalls the real installers. The full test suite also
passes against the curated libVLC that ships in the release.

One limit applies to "a clean test machine". Windows 11 **Home** has no Windows Sandbox or
Hyper-V, so there was no separate machine. Instead, the installed program ran with a fully
stripped environment: Windows-only `PATH`, no Python or Babarify variables, and empty profile
folders. While it played, every module it had loaded was checked, and none came from the
repository or the Python environment. A run on a genuinely fresh PC is the first M11 beta
scenario (§6).

The final release is built from the committed tree (the build refuses uncommitted changes).
§2 records the final build's checksums (built from the accepted commit).

## Acceptance criteria (plan §8, M10)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | Install and uninstall succeed on a clean test machine | **PASS (clean environment; see above)** | Silent per-user install to a new folder: exit 0, version 0.9.0, 430 MB. Silent uninstall: program folder, uninstall entry and "Open with" keys removed; user data kept, as a silent uninstall should. An interactive uninstall asks whether to delete the data; the default answer keeps it. [`evidence/release_check.json`](evidence/release_check.json) |
| A2 | No development-only dependency is accidentally required | **PASS** | The installed app ran with Windows-only `PATH`, no `PYTHON*`/`BABARIFY_*` variables and empty profiles. Modules loaded from outside the install folder were only Windows fonts, Defender's scanner hook and the app's own database; none from the repository, `.venv` or `.engines`. A release ignores `BABARIFY_VLC_DIR` and loads libVLC only from its own folder, and mpv, pytest and PyInstaller are not bundled. |
| A3 | Packaged playback works without a development environment | **PASS** | In that clean environment the installed app played H.264 1080p: its log records "state=playing" at the end of each smoke run (install, upgrade, rollback). The packaged AI worker transcribed test speech (7 lines, English). The full suite also passes against the curated engine (**562 passed**). |
| A4 | All distributed binaries and licences reviewed | **PASS** | Every libVLC plugin's declared licence read from the DLL itself: 360 plugins, LGPL-2.1+ or GPL-2.0+, none unknown. 101 excluded, each with a reason (§3). 27 Python distributions found from the runtime dependency closure, all GPL-3-compatible (MIT, BSD, Apache-2.0, MPL-2.0, LGPL, PSF). Licence texts are collected into `licenses\` and `THIRD_PARTY_NOTICES.txt`. |
| A5 | Update and rollback behaviour tested | **PASS** | 0.9.0 → 0.9.1 (upgrade in place, version 0.9.1, data kept, plays) → 0.9.0 (rollback, version 0.9.0, data kept, plays). The installer replaces the whole program folder, so no old file is left behind. |
| A6 | No release-blocking security or stability issue remains | **PASS** | §4 review: one issue found and fixed (R44, untrusted text shown as HTML). The plugin set was cut by 101 (capture, discs, servers, online services). The release ignores DLL-path environment overrides. Local crash log. Full suite green. |
| A7 | Release artifacts and checksums recorded | **PASS** | `SHA256SUMS.txt` and a per-file manifest (size, SHA-256, commit) are written by the build (§2). The source archive is the `git archive` of the built commit. |

### Deliverables

| Deliverable | Status |
|---|---|
| Production installer and versioning strategy | ✅ `BabarifyFrame-0.9.0-setup.exe`: per-user, no admin, Start menu, optional desktop icon; optional "Local AI features" component (Compact saves about 240 MB). Versioning in [RELEASING.md](../../RELEASING.md) |
| File associations only with consent or Windows conventions | ✅ Optional task (unticked) adds *Open with* entries and a *Default apps* registration; never changes defaults (verified: `.mp4` default unchanged after install and uninstall) |
| Clean install, upgrade, repair, uninstall | ✅ Tested (A1, A5). Repair = run the same installer again (replaces the program folder) |
| Signed binaries/installer where feasible | ⚠️ Not feasible now (no certificate). Documented; SHA-256 checksums published; the signing procedure is in RELEASING.md |
| Dependency and third-party notice bundle | ✅ `THIRD_PARTY_NOTICES.txt`, `licenses\` (generated by `tools/notices.py`) |
| Licence compliance review | ✅ §3; GPL-3.0-or-later chosen; `LICENSE` (official text, SHA-256 verified) |
| Update integrity and rollback strategy | ✅ No auto-updater (privacy); checksummed installers; tested rollback |
| Crash diagnostics and privacy documentation | ✅ Local `app.log` and `crash.log` (faulthandler); [PRIVACY.md](../../PRIVACY.md) |
| Release notes and user documentation | ✅ [release-notes/0.9.0.md](../../release-notes/0.9.0.md), README, in-app F1 |

## 1. Tests

| Check | Result |
|---|---|
| Full default suite, development engine | **563 passed**, 0 failed (one new: R44) — see §1.1 |
| Full default suite against the **curated** libVLC (`BABARIFY_VLC_DIR=build/engines/vlc`) | **562 passed**, 0 failed (before R44's test was added) |
| `tools/release_check.py` (0.9.0 ↔ 0.9.1) | all items true ([`evidence/release_check.json`](evidence/release_check.json)) |
| ruff, strict mypy | clean |

### 1.1 Final run

After all M10 changes: ruff (check and format) clean, strict mypy clean, full default suite
**563 passed**, 72 skipped (mpv opt-in, missing optional media), 0 failed, no crash
(`-X faulthandler`).

## 2. Release artifacts (final build from commit `a307656`, clean tree)

| File | Size | SHA-256 |
|---|---|---|
| BabarifyFrame-0.9.0-setup.exe | 120.7 MB | `5ebdffe13a43d2411635e89d8499c5fe138cfaf906e77d0737cc86efe8737467` |
| BabarifyFrame-0.9.0-source.zip | 14.6 MB | `01f03c9a90af5416ee67f91d23f06a88d58ca646ff4ee6705a05f4b1b5ccb4a7` |
| BabarifyFrame-0.9.0-manifest.json | 0.1 MB | `978186f4ba40df55e07da7bc53ef52456ced9e68ccec541eb7df2ed0cb76adf0` |

This exact installer passed the release check again after the build: install, clean-environment
playback, AI worker, repair install (same version over itself), uninstall
([`evidence/release_check_final.json`](evidence/release_check_final.json)). The upgrade and
rollback evidence (0.9.0 ↔ 0.9.1) is from the trial build of the same code
([`evidence/release_check.json`](evidence/release_check.json)). The artifacts are in
`release/0.9.0/` on the build PC (not in git); the checksums above are the record.

Installed size: 186 MB without the AI component, 430 MB with it (685 files). The AI component
is about 240 MB (CTranslate2, onnxruntime, PyAV, numpy).

## 3. Licence and binary review

**Babarify Frame:** GPL-3.0-or-later (`LICENSE`). Every distributed component's licence is
GPL-3-compatible. Qt/PySide6 are used under the LGPL v3 as separate, replaceable DLLs.

**libVLC 3.0.24 plugins.** Each plugin's own licence string was read from the DLL without
running its code (`vlc_entry_license__3_0_0f`; `tools/vlc_plugins.py audit`). Results:
- Licences: 327 LGPL-2.1+ and 33 GPL-2.0+; none unknown.
- Shipped: 259. Excluded: 101, each with a reason recorded in [`evidence/plugins.json`](evidence/plugins.json):
  - **Legal:** DVD and Blu-ray access (CSS/AACS) and ARIB conditional access.
  - **Privacy and online services:** Last.fm scrobbler, AcoustID fingerprinting, add-on
    repository, cover-art and lyrics fetchers, service discovery.
  - **Attack surface:** camera, microphone, screen and TV capture; network protocols
    Babarify does not offer (ftp, sftp, smb, nfs, mms, udp, rtp, srt, rist, vnc…); streaming
    servers and Chromecast; remote-control interfaces; Lua; `vlc://`; Adobe HDS (it would
    fetch around the stream proxy).
  - **Unused:** encoders, stream outputs and muxers except WAV for the AI worker, and
    VLC's own GUI.

The declared licences cover each module's own code. Third-party libraries linked into plugins
(FFmpeg and others) are listed in VLC's `COPYING.txt`, which ships in `licenses\libvlc`.

**Source:** the release ships `-source.zip`, the corresponding source for Babarify Frame.
The notices link the sources of bundled components and include a three-year source offer
(GPL v3 §6).

**Owner actions before public distribution:**
1. Publish the source archive next to the installer. The repository is currently marked
   private (`Private :: Do Not Upload`).
2. Consider mirroring the VLC 3.0.24 source tarball with the release, rather than relying
   on VideoLAN's server.
3. Codec patents are outside this review (M1 §4).

## 4. Security and stability review

| Area | Finding | Action |
|---|---|---|
| Untrusted text in the UI | Labels auto-detected rich text: a server error message, chapter title or `%3C…` in a stream address could render HTML (e.g. a local `file:` image) | **Fixed (R44):** plain text for every label that shows external text; test added |
| DLL loading | Release could be pointed at other DLLs by `BABARIFY_VLC_DIR` | **Fixed:** frozen builds use only their own `engines` folder; PyInstaller's bootloader restricts the DLL search path to the app folder |
| Bundled engine surface | Capture devices, servers, scripting, online lookups reachable in the full plugin set | **Fixed:** 101 plugins removed (§3); the suite passes on the curated set |
| Network | Covered in M8 (stream proxy, redirects, playlists, `--no-lua`) and M9 (pinned, hash-checked model downloads) | Re-checked; unchanged |
| Parsing untrusted files | libVLC parses media and subtitles; subtitle files capped at 20 MB; settings JSON and library rows validated; SQL parameterised; FTS queries sanitised | No change. **Keep libVLC current:** watch VideoLAN security advisories (3.0.24 is the build shipped) |
| Code patterns | No `shell=True`, `eval`/`exec`, `pickle`, `yaml.load`, `os.system` or temp-name races in `src/` | — |
| Crash diagnostics | Native crashes left no trace in a windowed release | **Added:** `crash.log` via faulthandler, unhandled Python errors, engine start-up and failure logged; local only |
| Known-vulnerability scan of Python dependencies | Not run: `pip-audit` sends the dependency list to an online database, which needs the owner's OK | **Owner action:** run `pip-audit` before public release |

## 5. Known limitations

1. **Unsigned:** SmartScreen warns on first run; verify with `SHA256SUMS.txt`.
2. **First launch after installing or updating:** the engine took 13 s to start, then 0.2 s
   on later launches. This matches Windows scanning the newly installed DLLs. The app shows
   "Starting playback engine…" meanwhile.
3. **No separate clean machine** (Windows 11 Home); clean-environment run instead (above).
4. **Interactive uninstall "delete my data: Yes"** was not automated (message box); the
   folders it removes are the documented user-data locations. Verify by hand in M11.
5. **Size:** 121 MB installer; AI component optional.
6. mpv (alternate engine) is not shipped.

## 6. For M11 (beta)

Install on a fresh Windows 10 and 11 PC (or Sandbox on Pro), including SmartScreen and an
interactive uninstall with data deletion; `pip-audit`; publish the source archive; decide on
signing.

## 7. Changes

- `LICENSE` (GPL-3.0), `pyproject.toml` licence and version 0.9.0.
- `packaging/`: `babarify.spec`, `installer.iss`, entry scripts.
- `tools/`: `build_release.py`, `vlc_plugins.py`, `notices.py`, `release_check.py`.
- `src/`: `app_log.py` (local logs and crash records); frozen-build engine lookup and AI
  worker path; optional AI component detection; `widgets.plain_text` (R44); engine start-up
  logging; smoke-test state logging; proxy user agent from the version.
- Docs: [RELEASING.md](../../RELEASING.md), [PRIVACY.md](../../PRIVACY.md),
  [release-notes/0.9.0.md](../../release-notes/0.9.0.md), README licence section,
  architecture overview, R44.
