# M16 Baseline Report — Ongoing Maintenance

**Date:** 2026-11-03 · **Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Status: **ongoing**; baseline accepted by the owner on 2026-11-03

M16 has no end: its criteria apply to every future release, and no release has been made under them yet.
This report covers the baseline the owner chose. It doesn't declare M16 complete, and
**nothing here moves Windows 1.0, the Android release or iOS forward.** Those wait on the owner's decisions.

## Delivered

| Owner's choice | What exists |
|---|---|
| Automatic checks | `.github/workflows/checks.yml`: Windows lint, types and tests; Android unit tests and lint |
| Monthly security check | `.github/workflows/security.yml`, auditing `requirements/windows-runtime.txt`, written by `tools/write_runtime_pins.py` |
| Changelog and support guide | `CHANGELOG.md`, `SECURITY.md`, [`docs/SUPPORT.md`](../../SUPPORT.md) |

`tests/unit/test_release_records.py` fails if a version has no changelog entry, or if the pins don't match the
Windows version. That guards part of the criterion "each release has a changelog".

## Evidence

| Check | Result |
|---|---|
| Windows suite on the build PC | 568 passed, 72 skipped, 0 failed |
| Checks on GitHub, branch `m16-baseline`: Windows job | ruff and mypy clean; **410 passed, 230 skipped**, 0 failed |
| Checks on GitHub: Android job | unit tests and lint passed |
| Security check on GitHub | no known vulnerabilities in the 27 pinned packages |
| Security check can fail | On the build PC, the same command with an old `requests==2.5.0` exits 1 and lists advisories. A workflow failure itself hasn't been seen |

## Limits

- **GitHub's Windows job has no libVLC or generated media.** That accounts for the 230 skipped tests, so **no real
  playback runs there.** A green result doesn't mean playback works. The full suite still runs on the build PC.
- **Android's device tests don't run on GitHub,** only unit tests and lint. Device tests need a phone or an emulator.
- **The schedule itself hasn't fired yet.** The audit ran through a push trigger; the first scheduled run is due on
  the 3rd of a month. GitHub disables schedules after 60 days without repository activity.
- **The audit covers Python packages only.** libVLC, Android and iOS libraries are watched by hand
  ([support guide](../../SUPPORT.md)), and nobody is doing so automatically.
- **Pins were taken from the build environment,** not read from the 0.9.1 installer. The count matches M11's
  27 packages, and the environment hasn't been rebuilt since, but no package-by-package comparison was made.
- **GPU driver and OS regression testing** (a plan item) isn't automated, and depends on the real-hardware runs.
- **Localization, Linux and macOS, and profiling work** weren't started; nothing yet justifies them.

## Next

M16's other items are triggered by events: user reports, new OS versions, advisories. See the
[support guide](../../SUPPORT.md).
