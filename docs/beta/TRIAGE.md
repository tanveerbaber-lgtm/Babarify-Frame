# Beta triage process (M11)

Every report gets a severity and a reproducibility class, from the issue form and confirmed by
the maintainer within 3 working days. Release readiness is decided from these records
(`python tools/triage_summary.py`), not from download counts.

## Severity

| Class | Meaning | Examples | Release rule |
|---|---|---|---|
| **S1** | Crash, hang, data loss, security or privacy problem, cannot install/uninstall, a file plays wrong silently | access violation; library lost; a stream opens a local file; uninstall leaves the program | **Blocks the release** until fixed and verified |
| **S2** | A main task fails with no workaround | a common format will not play; subtitles never show; settings not saved | **Blocks the release** unless the owner accepts it in writing with a documented workaround |
| **S3** | Wrong, but there is a workaround | a control in the wrong state; a misleading message | Fix if time allows; listed in Known issues otherwise |
| **S4** | Cosmetic, wording | alignment, typo, colour | Batched; never blocks |

Accessibility problems that stop a keyboard or screen-reader user from completing a main task
are **S2**.

## Reproducibility

| Class | Meaning | Handling |
|---|---|---|
| **R-always** | Every time, with the steps given | Reproduce, fix, add a regression test |
| **R-often** | More than half the time | Same; the test repeats the scenario (see the M7 soak) |
| **R-sometimes** | Occasionally | Ask for the report text and logs; try the soak tool; keep open |
| **R-once** | Seen once, not again | Keep open 2 weeks with the reporter's details; S1 cases (crashes) still need `crash.log` analysis |

## Labels

`beta`, `needs-triage`, `bug`, `feedback`, `S1`…`S4`, `R-always`, `R-often`, `R-sometimes`,
`R-once`, `area:…` (from the form), `fixed-in:<version>`, `known-issue`.

## Workflow

1. **New** (`needs-triage`): read, confirm or correct severity and reproducibility, add labels,
   remove `needs-triage`. Ask for the *Report a problem* text if missing. Never ask for private
   files; if a sample is needed, ask for a short, non-private clip the reporter is happy to share.
2. **Reproduce** on the development PC. If it cannot be reproduced, record what was tried.
3. **Fix** with a regression test that fails before the fix (`tests/`), and an entry in
   `docs/testing/regressions.md` (R-number) for S1/S2 and for anything not obvious.
4. **Verify** in a release build (`tools/build_release.py` and `tools/release_check.py`); label
   `fixed-in:<version>` and ask the reporter to confirm.
5. **Close** when the reporter confirms or after 2 weeks without an answer.

## Release readiness (beta → 1.0)

Ready when, from `tools/triage_summary.py`: no open S1; no open S2 without the owner's written
acceptance; every fixed S1/S2 has a regression test; the test scenarios
(`TEST_SCENARIOS.md`) have passed on at least one fresh Windows 10 and one fresh Windows 11
PC; and Known issues is up to date.

## Privacy

Reports are public issues. The form asks reporters to leave out private details, and the app's
report text excludes file names and logs unless the reporter adds them. Remove private data
from an issue as soon as it is noticed (edit the issue; ask GitHub support to purge the edit
history if needed). Security and privacy problems go to private vulnerability reporting.
