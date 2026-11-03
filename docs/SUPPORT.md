# Support and maintenance guide (M16)

How reports and updates are handled, for the maintainer.

## Reports

1. **New issue:** classify it as in [TRIAGE.md](beta/TRIAGE.md), with severity S1–S4 and reproducibility.
   `python tools/triage_summary.py` shows what blocks a release.
2. **Security or privacy report:** these arrive privately ([SECURITY.md](../SECURITY.md)). Fix and
   release before discussing details in public.
3. **Fix:** add a test that fails without the fix, and record it in the
   [regression catalog](testing/regressions.md).
4. **Requests:** a feature must not weaken privacy or core playback (plan §8, M16).

## Before every release

- Follow [RELEASING.md](RELEASING.md): tested build, dependency and licence review, changelog entry.
- Windows: run `python tools/write_runtime_pins.py` from the build environment, so the monthly check
  audits what ships.
- A green **Checks** run isn't enough. Playback, device and installer checks need the build PC and real
  devices.

## Automatic checks

| Workflow | When | Covers | Doesn't cover |
|---|---|---|---|
| **Checks** | Push to `main` or a milestone branch, pull requests | Lint, types, tests without libVLC, Android unit tests and lint | Real playback, devices, installers |
| **Monthly security check** | 3rd of each month, or by hand | Known vulnerabilities in the Python packages Windows ships | libVLC, Android and iOS libraries |

- GitHub usually notifies you of a failed run by email; check your notification settings.
- **GitHub disables scheduled workflows after 60 days with no repository activity.** It warns by email,
  and any commit or re-enabling on the Actions page restarts it.

## What to watch by hand

There's no automatic alert for these:

| Component | Where | Used by |
|---|---|---|
| libVLC 3.0.x | [VideoLAN security advisories](https://www.videolan.org/security/) | Windows |
| libVLC for Android | Same, and [Maven Central versions](https://central.sonatype.com/artifact/org.videolan.android/libvlc-all) | Android |
| Windows and Android updates | New OS versions may change behaviour; rerun the release and device checks | All |

## Open owner decisions

See the plan's *Current status*: Windows 1.0, the Android signing key and licence items, and the iOS
licence route.
