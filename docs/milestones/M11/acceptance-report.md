# M11 Acceptance Report — Public Beta and User Feedback (preparation)

**Date:** 2026-11-01 · **Beta build:** 0.9.1 · **Prepared by:** Claude (Claude Code) ·
**Decision owner:** Tanveer Baber

## Decision: **CONDITIONAL** — accepted by the owner on 2026-11-01 (beta ready to start; PASS after the beta has run)

Owner decisions: feedback goes to **GitHub Issues**; **pip-audit** approved and run.

Everything M11 asks to be *prepared* is done:
- the beta build, with a fix and a new feature;
- a structured feedback channel, in the repository and in the app;
- the known-issues page and test scenarios;
- the triage process, with a summary tool;
- an accessibility review, which found one defect, now fixed;
- a dependency vulnerability audit.

M11's **acceptance criteria are about a beta that has run**: feedback categorised, critical
issues fixed, readiness decided from evidence. No tester has used the app yet, so those
criteria cannot be met today, and claiming them would be wrong.

**Condition for PASS:** run the beta (owner actions in §5) until the release-readiness rules
in `docs/beta/TRIAGE.md` are met, then decide from `tools/triage_summary.py`.

## Acceptance criteria (plan §8, M11)

| # | Criterion | Status | Evidence / what remains |
|---|---|---|---|
| A1 | Feedback is categorised by severity and reproducibility | **Ready** | Issue forms require severity (S1–S4) and reproducibility, with definitions in `TRIAGE.md`; `triage_summary.py` counts by both (tested on sample data). Remains: real reports. |
| A2 | Critical issues are fixed or block release | **Ready** | Rules: open S1 always blocks; open S2 blocks unless the owner accepts it; each fixed S1/S2 needs a regression test. The tool lists blockers and exits 1 while any remain. Remains: the beta itself. |
| A3 | User data is not collected beyond the documented and consented process | **Met by design** | No telemetry, crash upload or account. The only data received is what a tester writes into an issue. *Report a problem* sends nothing and leaves out file names and logs unless ticked; the profile path is redacted (`test_report_contains_versions_but_no_private_details_by_default`). The forms ask for a privacy check, and there is a private channel for security or privacy problems. |
| A4 | Release readiness is decided from evidence, not download counts | **Ready** | Readiness rules in `TRIAGE.md` (no open S1, no unaccepted S2, regression tests, scenarios passed on fresh Windows 10 and 11); `triage_summary.py` applies them. Remains: the decision itself. |

### Deliverables

| Deliverable | Status |
|---|---|
| Beta build and known-issues page | ✅ 0.9.1 (§2); [KNOWN_ISSUES.md](../../beta/KNOWN_ISSUES.md); [BETA_GUIDE.md](../../beta/BETA_GUIDE.md) |
| Structured feedback channel | ✅ `.github/ISSUE_TEMPLATE/` (Problem report, Feedback, private security link); *Help → Report a problem* |
| Test scenarios: installation, playback, subtitles, library, settings | ✅ [TEST_SCENARIOS.md](../../beta/TEST_SCENARIOS.md): 31 scenarios with IDs (INS, PLY, SUB, LIB, SET, ACC, PRV) |
| Triage process and regression tests | ✅ [TRIAGE.md](../../beta/TRIAGE.md), `tools/triage_summary.py`; regression-test rule (R-numbers continue) |
| Accessibility and usability review | ✅ §3; one defect fixed (R45); Narrator and contrast-theme checks are tester scenarios ACC-2 and ACC-4 |

## 1. Tests

| Check | Result |
|---|---|
| Full default suite (0.9.1) | **565 passed**, 72 skipped, 0 failed |
| Report a problem: `tests/ui/test_report_ui.py` | 2 passed |
| Accessibility audit: `tools/a11y_audit.py` | 0 problems; all contrast pairs pass ([`evidence/a11y_audit.json`](evidence/a11y_audit.json)) |
| Release check, 0.9.0 → 0.9.1 → 0.9.0 (trial build) | all items pass: install, clean-environment playback in all three versions, AI worker, upgrade and rollback with data kept, uninstall ([`evidence/release_check.json`](evidence/release_check.json)) |
| ruff, strict mypy | clean |

## 2. Beta build

0.9.1 = 0.9.0 + *Report a problem* + the contrast fix (R45). Release notes:
[0.9.1.md](../../release-notes/0.9.1.md). Final build from commit `372f48f` (clean tree):

| File | Size | SHA-256 |
|---|---|---|
| BabarifyFrame-0.9.1-setup.exe | 122.4 MB | `b54e7a7dd3997caa3c791073947443df1b5c6eeb58fdefb97e4bd92c733c9220` |
| BabarifyFrame-0.9.1-source.zip | 14.8 MB | `7e6f783d0927e514b86d199e3d65fa5f1889267903097d797647d32aa5c28051` |
| BabarifyFrame-0.9.1-manifest.json | 0.1 MB | `ca0d637328cc3a7cb06f9a881193c622ee2f91dcfe83e2abfae7351294fb6c03` |

This installer passed the release check (0.9.0 → 0.9.1 → 0.9.0: install, clean-environment
playback in all three, AI worker, data kept, uninstall;
[`evidence/release_check_final.json`](evidence/release_check_final.json)). 685 files, as in
0.9.0. The artifacts are in `release/0.9.1/` on the build PC (not in git).

## 3. Accessibility and usability review

Automated (`tools/a11y_audit.py`, every page and dialog of the running app):
- **Names:** every interactive control has a name a screen reader can announce: an
  accessible name, its own text, or its form label. **0 missing.**
- **Keyboard:** every dialog control can take focus. The control bar's buttons are
  deliberately not Tab stops; every action has a key and a menu entry (F1 lists them).
- **Contrast (WCAG 2.1):**
  - Body text: 13.6–16.7:1.
  - Muted text: 5.6–6.9:1.
  - Accent, warning, error and success colours: 7.1–10.9:1.
  - Focus ring: 10:1.
  - **Control outlines were 1.37:1, below the 3:1 that 1.4.11 asks for.** Text fields,
    drop-downs, check boxes, lists, buttons, slider tracks and scroll bars blended into the
    panel. Fixed with a separate control-border colour, now 3.2–4.0:1 on every surface (R45;
    evidence `settings_controls.png`).

Not automatable here, so assigned to testers:
- **ACC-2:** Narrator announcing controls.
- **ACC-3:** display scale 150 % and text size 125 %.
- **ACC-4:** Windows contrast themes. The app keeps its own dark theme, recorded as a known
  issue.
- **ACC-1:** a keyboard-only session.

Build hygiene (found while building the beta): installing pip-audit put `certifi`,
`charset-normalizer` and `tomli` into the development environment, and PyInstaller bundled them
through optional imports (17 extra files). They are now excluded, and the notices tool
evaluates dependency conditions instead of listing `tomli` for Python < 3.11 (R46). The
manifest diff between releases is the check: 0.9.1 has the same 685 files as 0.9.0.

Usability: earlier milestones fixed several findings from screenshot reviews (R31, R38, R39,
R42). Further usability feedback is the purpose of the beta's *Feedback* form.

## 4. Dependency vulnerability audit (pip-audit, approved by the owner)

`pip-audit` 2.x checked the bundled Python packages (the runtime dependency closure from
`tools/notices.py`) against the PyPI/OSV advisory databases: **no known vulnerabilities**
in 27 packages. `packaging` 26.3 was not checked: pip-audit leaves out packages it uses
itself. It is a current, pure-Python version-parsing library that handles no untrusted input
here. Only package names and versions were sent. libVLC 3.0.24 is not covered by pip-audit:
watch VideoLAN's security advisories (RELEASING.md).

## 5. Starting the beta

**Started 2026-11-02.** Done with the owner's approval: the repository is public (history scanned
first: no secrets or credential files in any commit); triage labels created; private vulnerability
reporting enabled; [v0.9.1 published as a pre-release](https://github.com/tanveerbaber-lgtm/Babarify-Frame/releases/tag/v0.9.1)
(tag at the built commit, installer, source archive, manifest, checksums). Verified without a
GitHub login: the downloaded installer matches its SHA-256; the guide, scenarios, known issues,
privacy notice, private reporting page and VLC source link all open. No tester has reported yet,
so the condition for PASS stands.

Remaining: fresh-PC scenarios (item 5) and inviting testers. The original checklist:

1. Give testers access: make the repository public, or invite them as collaborators.
2. Create the triage labels (once):
   `gh label create S1 --color B60205`, then the same for `S2` (D93F0B), `S3` (FBCA04) and
   `S4` (C2E0C6); `R-always`, `R-often`, `R-sometimes`, `R-once`; `beta`, `needs-triage`,
   `feedback`, `known-issue`, `accepted-by-owner`.
3. Enable *Private vulnerability reporting* (repository Settings → Security). The new-issue
   page links to it.
4. Publish the 0.9.1 release: the installer, the source archive (GPL) and `SHA256SUMS.txt`.
5. First scenarios on fresh PCs: INS-1…7 on Windows 10 and 11 (this closes M10's
   clean-machine limit); ACC-2 with Narrator.

## 6. Changes

- `src/`: `ui/report.py` (*Help → Report a problem*), `CONTROL_BORDER` in the theme (R45),
  version 0.9.1.
- `.github/ISSUE_TEMPLATE/`: Problem report, Feedback, config.
- `docs/beta/`: BETA_GUIDE, TEST_SCENARIOS, TRIAGE, KNOWN_ISSUES; release notes 0.9.1; R45.
- `tools/`: `a11y_audit.py`, `triage_summary.py`.
- Tests: `tests/ui/test_report_ui.py`.
