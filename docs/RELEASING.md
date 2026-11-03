# Releasing Babarify Frame (M10)

## Versioning

Semantic versioning, `MAJOR.MINOR.PATCH`, in one place: `babarify_frame.__version__` (and the
same value in `pyproject.toml`). The installer, both executables' version resources and the
release folder take it from there.

- `0.9.x`: release candidates for the public beta (M11). `1.0.0`: first general release.
- PATCH: fixes only, no data format change. MINOR: features; may add a library schema
  migration. MAJOR: incompatible change in user data (not planned).
- Library database: versioned schema (`PRAGMA user_version`, M6). A newer version migrates
  forward in one transaction. An older version never modifies a newer database: it starts with
  an empty in-memory library and says why. Settings: unknown keys are ignored and invalid
  values fall back to defaults, so both directions work.

## Building

Prerequisites (development PC): the project's `.venv` with the `dev` extra, PyInstaller 6,
Inno Setup 6 (per-user install, `%LOCALAPPDATA%\Programs\Inno Setup 6`), the libVLC 3.0.24
engine in `.engines/vlc` (README), git.

1. Update `__version__`, `pyproject.toml` and add `docs/release-notes/<version>.md`.
2. Commit. The build refuses a dirty tree (except `--allow-dirty` for test builds).
3. `python tools/build_release.py` writes `release/<version>/`:
   - `BabarifyFrame-<version>-setup.exe`: the installer
   - `BabarifyFrame-<version>-source.zip`: `git archive` of the built commit (GPL source)
   - `BabarifyFrame-<version>-manifest.json`: every shipped file with size and SHA-256, and
     the commit
   - `SHA256SUMS.txt`
4. `python tools/release_check.py <previous-setup.exe> <new-setup.exe>`: install, run in a
   clean environment, AI worker, upgrade, rollback and uninstall checks.
5. Record the checksums in the milestone report and the release page; publish the source
   archive alongside the installer.

What the build does: curates libVLC (`tools/vlc_plugins.py`: 259 of 360 plugins, with reasons
for every exclusion and each plugin's declared licence), freezes the app and the AI worker with
PyInstaller (`packaging/babarify.spec`), adds `LICENSE.txt`, `THIRD_PARTY_NOTICES.txt`,
`licenses\`, `PRIVACY.txt` and the release notes (`tools/notices.py`), and compiles
`packaging/installer.iss`.

## Updates and rollback

There is no automatic updater and no update check (privacy: the app makes no network
connection on its own). Updating means running a newer installer:

- **Integrity:** users verify the installer against `SHA256SUMS.txt` (unsigned builds; see
  below). The installer replaces the whole program folder (`[InstallDelete]` of `_internal`,
  `engines`, `ai`), so no file of an older version is left behind.
- **Upgrade:** same AppId, so it installs in place; running copies are closed by Windows
  Restart Manager first. User data is never touched by the installer.
- **Rollback:** run the older installer; it replaces the program the same way. Data
  compatibility as described under Versioning. Keep previous installers available.
- Tested by `tools/release_check.py` (0.9.0 → 0.9.1 → 0.9.0).

## Signing

Releases are **not code-signed** yet (no certificate). Consequences: SmartScreen warns on first
run, and integrity relies on the published SHA-256 checksums. Adding signing later: sign both
executables in `build/dist` and the installer with `signtool sign /fd sha256 /tr <timestamp
server> /td sha256`. Run it by hand, so the private key never enters the build scripts. The
Windows SDK's `signtool.exe` is available on the development PC.

## Licence obligations (GPL-3.0-or-later)

- `LICENSE.txt` and `THIRD_PARTY_NOTICES.txt` (with `licenses\`) are in the program folder.
- The corresponding source of Babarify Frame for each release is the published
  `-source.zip`. Sources of bundled components are listed in the notices (VLC 3.0.24 source
  tarball, PyPI source distributions, Qt/PySide6 sources); on request the maintainer provides
  them for at least three years.
- Qt/PySide6 (LGPL v3) stay separate DLLs in `_internal\PySide6`, replaceable by the user.
- Excluded for legal reasons: DVD/Blu-ray access (CSS/AACS), ARIB conditional access.

## Android (M13)

Android 10 or later, published on GitHub as APKs for `arm64-v8a` and `armeabi-v7a`.

1. Update `versionName` and `versionCode` in `android/player/app/build.gradle.kts`.
2. Run the device tests on the supported devices: `gradlew connectedDebugAndroidTest` in `android/player`.
3. Set `BABARIFY_KEYSTORE`, `BABARIFY_KEY_ALIAS`, `BABARIFY_KEYSTORE_PASSWORD` and
   `BABARIFY_KEY_PASSWORD`, then, from a clean commit, run `python tools/build_android_release.py`.
4. Test the signed APK on a real phone before publishing.

- **The signing key never goes in the repository.** Losing it means people can't update without
  reinstalling, so it needs its own backup.
- `THIRD_PARTY_NOTICES.txt` under `android/player/app/src/main/assets/licenses/` must match
  `gradlew :app:dependencies --configuration releaseRuntimeClasspath`.
- Keep the libVLC source matching the release available for as long as it is distributed
  (VideoLAN tag `libvlc-<version>` in `vlc-android`; see the M13 report for what remains open).
