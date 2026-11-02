# M12 — Mobile licensing and packaging review

This is an engineering review and not legal advice. The project is GPL-3.0-or-later (owner decision,
M10). Have a lawyer review it if distribution becomes commercial or goes through a store.

## Direct dependencies

| Component | Version | Licence declared in its POM | With GPL-3.0-or-later |
|---|---|---|---|
| `org.videolan.android:libvlc-all` | 3.7.7 | LGPL-2.1 | Compatible, subject to the check below |
| `androidx.media3:media3-exoplayer` | 1.11.1 | Apache-2.0 | Compatible with GPLv3 |
| `androidx.legacy:legacy-support-v4`, `androidx.annotation` (via libVLC) | 1.0.0, 1.7.1 | Apache-2.0 *(expected for AndroidX; not read from each POM)* | Compatible with GPLv3 |
| Kotlin standard library | 2.2.10 | Apache-2.0 *(expected; not read from the POM)* | Compatible with GPLv3 |

Dependency trees came from `gradlew :app:dependencies` on the release classpaths.

## Findings

1. **libVLC's real licence set is not settled by its POM.** The POM says LGPL-2.1, but
   `libvlc-all` packs its plugins into a single 45.9 MB `libvlc.so`, so the APK doesn't show which
   components are inside. The desktop review (M1) found GPL-licensed plugins in VLC's builds, and the
   same should be assumed here until checked. A GPL-3.0-or-later app can include GPL-2.0-or-later
   code, so this probably doesn't block anything, but **M13 must list the contents from VideoLAN's
   build configuration and confirm no GPL-2.0-only code is included.**
2. **The APK contains no licence files.** No licence or notice file was found in the libVLC APK. A
   release must add them, as `tools/notices.py` does on Windows.
3. **Source must be offered.** A release must offer our source and the corresponding libVLC source.
   The project is at `code.videolan.org/videolan/libvlcjni`; M13 must confirm that source matching
   3.7.7 is available and record it, as M10 did for VLC 3.0.24.
4. **Patent-encumbered formats.** H.264, HEVC, AC-3, MPEG-2 and others may carry patent licensing
   questions in some countries, and libVLC's software decoders make this more direct than relying on
   the phone's licensed decoders. This was not resolved on Windows either; it needs a decision from
   the owner, with advice if needed, before store distribution.

## Packaging

| | Media3 | libVLC |
|---|---|---|
| arm64-v8a APK | 2.7 MB | 54.1 MB |
| armeabi-v7a APK | 2.7 MB | 39.9 MB |
| x86_64 APK | 2.7 MB | 61.9 MB |

- Shrinking was off and no optimisation was tried, so these are upper bounds for this configuration.
- `libc++_shared.so` is 9.3 MB of the arm64 size.
- Per-ABI APKs or an App Bundle avoid shipping every architecture. A single APK with all of them
  would be well over 150 MB with libVLC.
- The prototypes are signed with the debug key for measurement and are **not distributable**.

## Not reviewed

Google Play, F-Droid and sideloading policies, GPL obligations through a store, and app signing and
key custody. These belong to M13, once the owner has chosen how to distribute.
