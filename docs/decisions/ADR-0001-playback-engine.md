# ADR-0001: Playback engine for the Windows player

- **Status:** **Accepted (provisional)** — accepted by Tanveer Baber on 2026-10-27. Conditions N2–N5 remain open.
- **Date:** 2026-10-27
- **Deciders:** Tanveer Baber (owner). Prepared by Claude (Claude Code) from M1 evidence.
- **Evidence:** [benchmark report](../milestones/M1/benchmark-report.md),
  [licensing report](../milestones/M1/licensing-report.md),
  [environment report](../milestones/M1/environment-report.md)

## Context

M2 needs one engine behind the `PlaybackEngine` contract to deliver real playback.
Candidates: libVLC 3.0.24 (python-vlc) and libmpv 0.41-dev (python-mpv). Both were
prototyped as adapters and measured on one Windows 11 laptop (Intel UHD 620).

## Evidence summary

| Criterion | libVLC | mpv | Better on this evidence |
|---|---|---|---|
| Plays all 4 codecs, HW decoding where the GPU supports it | ✅ | ✅ | tie |
| Time to real playback | 0.59–0.85 s (HW codecs) | 0.60–0.68 s | tie |
| Seek→resume | 279–517 ms | 43–428 ms | **mpv** |
| Engine init per process | ~500 ms | ~90 ms | **mpv** |
| CPU | 9 % of 1 core | 8–12 % | tie |
| RAM on 4K HEVC | 924 MB | 468 MB | **mpv** |
| Dropped frames, 4K HEVC on UHD 620 | 0 | 16–40 per 8 s (renderer; `vo=gpu` ≈ 9) | **libVLC** |
| Track listing | ✅ (after binding workaround) | ✅ | tie |
| Error reporting for bad files | only via heuristic | precise | **mpv** |
| **Process stability (multi-instance)** | clean, 10/10 integration runs after the S2 fix | **access violation in every multi-instance process** (S1, root cause open) | **libVLC** |
| Threading model with Python | engine threads call Python → GIL hazards; needs strict "close before window" rule | Python pulls events; safer | **mpv** |
| API ergonomics / integration effort | 4 workarounds needed | clean properties/events | **mpv** |
| Licensing of evaluated builds | GPL bundle (plugins); trimmable by removing plugin DLLs | GPL static DLL; trimming needs a rebuild | slight **libVLC** (for M1-scale effort) |
| Mobile roadmap (M12+) | VideoLAN maintains libVLC for Android/iOS (*assumption, not verified in M1*) | libmpv used by mpv-android; iOS less established (*assumption*) | **libVLC** (unverified) |
| Version risk | libVLC 4.x will change the API (*assumption*) | dev build; fast-moving | both |

## Decision (proposed)

**Use libVLC for M2, provisionally**, behind the existing adapter, and keep the mpv
adapter in the repository as a maintained alternative.

Rationale: the two show-stopper-class issues are not symmetric. libVLC's deadlock (S2)
has a **known cause and a verified fix** (close the engine before its host window;
detach Python callbacks first), and its other problems have working adapter
workarounds. mpv's access violation (S1) is **unexplained**, reproduces in every process
that creates more than one instance, and a crash at exit would lose unsaved state
(history/resume) in later milestones. libVLC also rendered 4K HEVC without drops on the
weakest likely target GPU class. mpv is better on API quality, seek latency, memory and
start-up, which are real advantages but not reliability blockers.

## Why this is conditional, not final

The evidence is not sufficient for an irreversible choice:

1. **S1 may not be mpv's fault.** A minimal python-mpv script did not crash; the cause
   could be python-mpv 1.0.8, this third-party libmpv build, or adapter usage. If S1 is
   fixed, mpv wins most remaining criteria.
2. **One machine.** No AMD/NVIDIA display GPU, no Windows 10, no HDR/10-bit.
3. Mobile and libVLC 4.x statements above are unverified assumptions.

## Conditions and next tests (smallest first)

| # | Next action | Decides |
|---|---|---|
| N1 | Owner accepts or rejects this provisional choice for M2 | Unblocks M2 |
| N2 | Time-boxed (½ day) S1 root-cause: try python-mpv's latest release, a libmpv release build (not git), and mpv's render API instead of `wid` | Whether mpv returns as the leading candidate |
| N3 | Re-run `bench.py` on a second PC with a discrete NVIDIA/AMD display GPU (and Windows 10 if available) | Whether the 4K drop and stability findings generalise |
| N4 | Prototype a trimmed libVLC plugin set (local playback only, no DVD/Blu-ray/CAS/network) and re-run the integration suite | Feasibility of a distributable libVLC build (licensing report §5) |
| N5 | Check libVLC 4.x status and Android/iOS libVLC distribution terms | Long-term API and mobile risk |

## Consequences

- M2 implements playback with `LibVlcEngine`; UI code still depends only on
  `PlaybackEngine`, so switching engines remains a factory change plus adapter work.
- M2 must implement the architecture rule "close the engine before its host window"
  in `MainWindow.closeEvent` and anywhere the video widget is recreated.
- M2 must replace remaining prototype gaps: seek after end of media, and the brief
  PLAYING shown before libVLC open failures.
- Licensing: a release needs a custom libVLC plugin set and generated notices
  (licensing report §5); no binary is distributed before that.
- The mpv adapter, tests and benchmark stay runnable so N2/N3 can overturn this ADR
  with evidence. If they do, this ADR is superseded, not edited.
