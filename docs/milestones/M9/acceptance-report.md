# M9 Acceptance Report — Intelligent and Optional AI Features

**Date:** 2026-11-01 · **Engine:** libVLC 3.0.24 x64 · **Speech engine:** faster-whisper 1.2.1
(CTranslate2 4.8.4, int8 on the CPU) · **Machine:** i7-8565U (4 cores / 8 threads), no NVIDIA
GPU, Windows 11 · **Prepared by:** Claude (Claude Code) · **Decision owner:** Tanveer Baber

## Decision: **PASS** — accepted by the owner on 2026-11-01

Owner decisions: **local processing only**; features left to my choice. I built:
- **Speech-to-text subtitles**, the most useful AI feature that can run well on this PC.
- **Spoken-word search** across the generated subtitles, which is the plan's "local media
  search using user-approved speech/text indexes".

Subtitle discovery needs an online service, so the local-only rule excludes it. Translation
and summaries are not built (§4).

All seven acceptance criteria have evidence. The feature is off until switched on, and runs
entirely on this PC. The only network use is a model download the user confirms, pinned to a
revision and checked against SHA-256 hashes. Transcription runs in a separate process at
below-normal priority. While it ran, 1080p playback dropped no frames.

## Acceptance criteria (plan §8, M9)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| A1 | AI features are off until explicitly enabled | **PASS** | `Preferences.ai_enabled` defaults to False. The menu items are hidden and the dialogs refuse to open until *Settings → AI features* is switched on (`test_ai_is_off_until_switched_on`, `test_ai_is_off_by_default_and_values_are_checked`). Installing the Python packages does not turn anything on. |
| A2 | The UI explains whether processing is local or remote | **PASS** | The switch reads "Turn on AI features (they run on this PC)". The Settings card and the Generate dialog both state that processing is local and nothing is uploaded (evidence `settings_ai.png`, `generate_dialog.png`). |
| A3 | Remote processing discloses what is sent and to whom | **PASS (no remote processing)** | Nothing is processed remotely. The one network action, downloading a model, asks first and names the size, source address, revision and licence, and says "nothing about you or your media is sent" (`test_model_download_asks_first_then_installs`; a declined download does nothing). |
| A4 | No media or subtitle is uploaded silently | **PASS** | No code path sends media, audio or subtitles anywhere. The worker reads the file with libVLC on this PC and loads the model offline (`HF_HUB_OFFLINE`, telemetry off). The model download fetches only the four pinned model files. Generated subtitles stay in Babarify's own folder. |
| A5 | Output is labelled machine-generated | **PASS** | The file name `<name>.<language>.machine-generated.srt` shows in the subtitle track list. The dialog reports "… lines in English (machine-generated)" and warns that the result can contain mistakes. The search dialog says it searches machine-generated subtitles. |
| A6 | Users can disable features and remove associated data | **PASS** | Switching AI off hides the features and stops a running job (`test_cancel_and_switching_ai_off_stop_the_worker`). *Delete model* removes a model. *Delete all generated subtitles…* removes the files and the search index (`test_generated_subtitles_can_be_deleted`). Your media and other subtitles are never touched. |
| A7 | Costs, dependencies, licences and performance documented before enabling | **PASS** | §2 and §3 below; the Settings card shows model sizes and the licence. There is no money cost: no service, no account. |

### Deliverables

| Deliverable | Status |
|---|---|
| Speech-to-text subtitle generation (validated local provider) | ✅ Ctrl+Shift+G: language (or automatic detection), model, time estimate, progress, Stop; the result joins the subtitle tracks and can be reloaded later |
| Local media search, user-approved speech/text index | ✅ Ctrl+Shift+F: searches the generated subtitles (FTS5); opens the file 1 s before the words. Title search already existed in the Library (M6) |
| User-controlled processing and data deletion | ✅ Off by default; Stop; delete models; delete generated subtitles |
| Optional subtitle discovery from approved sources | ❌ Needs an online service; excluded by the local-only decision |
| AI-assisted subtitle translation | ❌ Not built (§4) |
| Optional scene or chapter summaries | ❌ Not built (§4) |

## 1. Test results

| Suite | Result |
|---|---|
| Cues, SRT, paths, model verification and download, index: `tests/unit/test_ai.py` | 23 passed |
| UI with a stand-in worker (same protocol; real job runner and process handling): `tests/ui/test_ai_ui.py` | 10 passed |
| Real worker, tiny model, speech synthesised on this PC: `tests/integration/test_ai_engine.py` | 5 passed: word error rate ≤ 10 % (0 % measured); first line within 0.6 s of the speech; worker at below-normal priority; clear errors for files without audio; playback unaffected |
| Library schema v4: `tests/unit/test_library_db.py` | 33 passed |
| Full default suite | **562 passed**, 72 skipped (mpv opt-in, missing optional media), 0 failed (524 before M9) |
| ruff and strict mypy | clean |

## 2. Measurements (`tools/ai_measure.py`; JSON in `tools/engine-benchmark/results/ai_measure.json`)

These are best-case numbers: clean synthetic English speech from Windows' own synthesiser.
Real recordings with music, noise, accents or several speakers will be less accurate.

| Model | Download | Speed, 164 s of speech (whole job) | Word errors (35 s sample) | First line vs. speech start |
|---|---|---|---|---|
| Tiny | 78 MB | **10× real time** (15.8 s) | 0 % | 0.23 s early |
| Base (default) | 148 MB | **6× real time** (26.7 s) | 0 % | 0.23 s early |

"Whole job" includes starting the worker, loading the model, reading the sound with libVLC
(about 200× real time) and recognition with 4 of the 8 threads. A two-hour film takes about
20 minutes with base, 12 with tiny. The dialog's estimate uses these measured speeds (R43).

Playback impact: H.264 1080p played for 8 s alone, then while base transcribed. 0 frames
were dropped in both runs, and playback position kept pace with the clock (ratio 1.00).

## 3. Dependencies, licences and costs

| Item | Version | Licence | Size | Notes |
|---|---|---|---|---|
| faster-whisper | 1.2.1 | MIT | small | Optional extra `ai` (`pip install -e .[ai]`) |
| CTranslate2 | 4.8.4 | MIT | ~40 MB | Inference engine (CPU, int8) |
| onnxruntime | 1.31.1 | MIT | ~15 MB | Voice-activity filter (Silero VAD, MIT, ships in faster-whisper) |
| huggingface_hub, tokenizers | 2.4.0, 0.23.3 | Apache-2.0 | small | Model download (only when confirmed); tokenizer |
| PyAV | 19.0.2 | BSD (bundles LGPL FFmpeg) | ~60 MB | Installed by faster-whisper but **never called**: libVLC reads the audio |
| numpy and others | — | BSD/MIT/Apache | — | 21 packages in total, about 160 MB in the environment |
| Whisper models (Systran conversions) | pinned revisions | MIT | 78 / 148 MB | Downloaded in the app after confirmation; checked against SHA-256 |

Money cost: none. No account, no API key, no service.

## 4. Not built, and why

- **Subtitle discovery:** every useful source (e.g. OpenSubtitles) is an online service with an
  account and API key, which the owner's local-only choice rules out.
- **Translation:** Whisper can turn speech in other languages into English text. It cannot be
  validated here, because the only speech this PC can produce is English (installed voices:
  David and Zira, en-US), and downloading test recordings was not approved. A local text
  translation model would be a further 100–300 MB download per language pair. I did not ship
  anything I could not measure.
- **Summaries:** a useful local summary needs a language model several gigabytes in size, far
  beyond this PC's comfortable range. Remote processing was declined.

## 5. Limitations

1. Accuracy depends on the recording (§2): treat generated subtitles as a draft, as the dialog
   says.
2. Speed: on this CPU base needs about a sixth of the film's length; there is no GPU
   acceleration (no NVIDIA GPU; CTranslate2's CUDA path is untested).
3. One job at a time, for the file that is open. Network streams are not transcribed (the
   stream would be downloaded again).
4. Generated subtitles are keyed to the file's path, like history: moving or renaming a file
   loses the link. Search still finds the text, but the file must be at its old path to play.
5. The worker is started as `python -m babarify_frame.ai.worker`. M10 packaging needs an
   entry for it in the frozen app.
6. Stop ends the worker process at once. Partial results are discarded, never saved.

## 6. Defects found and fixed

| ID | Defect | Fix |
|---|---|---|
| R40 | Automatically detected language not used in the file name (`.und.`) | Renamed once the language is known; regenerating replaces the old file |
| R41 | Worker ran at normal priority (silent `SetPriorityClass` failure on 64-bit) | Argument types declared; tested on the real worker process |
| R42 | Misleading "about 1 min", nested brackets, full-width button | Wording and size fixed (from evidence inspection) |
| R43 | Time estimate twice too optimistic for base | Estimates use measured end-to-end speed |

Also found during the spike: faster-whisper 1.2.1 does not work with PyAV 19 (removed
argument). The design avoids PyAV altogether: libVLC decodes the audio.

## 7. Changes

- `ai/` package: `models.py` (pinned models, verification, download, deletion), `subtitles.py`
  (cues, SRT, storage paths), `worker.py` (separate process).
- Library schema v4: `transcripts` and the FTS5 `transcript_cues`; `search_spoken`.
- UI: `ui/ai.py` (job runner, Generate dialog, spoken-word search, model download); Settings →
  AI features; *Audio & Subtitles → Generate subtitles (local AI)*; *View → Search spoken
  words*; preferences `ai_enabled`, `ai_model`, `ai_language`.
- `pyproject.toml`: optional extra `ai`; `.models/` (development models) ignored by git.
- Tools: `ai_speech.py` (local test speech), `ai_measure.py`, `ai_screenshot.py`; test helper
  `tests/fake_ai_worker.py`.
- Evidence ([`evidence/`](evidence/)): `settings_ai.png`, `generate_dialog.png`,
  `generate_done.png`, `machine_subtitles.png` (generated subtitles on the video),
  `spoken_search.png`. All inspected; three were retaken after R42.
