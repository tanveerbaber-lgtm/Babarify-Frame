# Regression catalog

Every defect found from M1 onward, what caused it, how it was fixed, and what now guards
it. A defect is only "closed" when an automated test (or, where automation is not
possible, a named tool) fails if it comes back. Test names refer to `tests/`.

| ID | Found | Symptom | Root cause | Fix | Guarded by |
|---|---|---|---|---|---|
| R1 | M1 | Process crash (access violation) when reading tracks | python-vlc's `Media.tracks_get()` struct layout is wrong for libVLC 3.0.24 x64 | Own ctypes definitions of the track structs | `test_tracks_are_listed`, `test_corpus_file_plays_with_correct_media_info` |
| R2 | M1 | Hardware decoder never detected | python-vlc `libvlc_log_get_context` needs out-params; the `TypeError` was swallowed in the log callback | Context lookup removed | `test_decoder_is_reported_once_decoding` |
| R3 | M1 | `play()` after `stop()` did nothing | READY → PLAYING is not a valid transition | `EngineBase.play()` reloads the selected media | `test_stop_returns_to_ready_and_play_restarts` (unit), `test_stop_then_play_restarts` (integration) |
| R4 | M1 | Rare crash or hang on close | A deferred engine call could run against a released handle | `EngineBase.close()` drains the worker before adapter teardown | `test_close_in_every_state_is_prompt` (8 states), `test_close_after_error_still_cleans_up` |
| R5 | M1 | Corrupt file shown as "ended" | libVLC reports unreadable files as Playing → EndReached, no error event | "Ended with nothing decoded" → `MEDIA_OPEN_FAILED` | `test_invalid_media_fails_without_playing_and_engine_recovers` |
| R6 | M1 | App froze on window close | Destroying the host window under a live libVLC video output deadlocks on the GIL (S2) | Close the engine before its window; detach the log callback first | `test_close_shuts_engine_down_before_window`, integration fixtures, `test_shutdown.py` |
| R7 | M1 | Access violation in processes that create several mpv instances | Not isolated (S1) | **Open** — mpv is the alternate engine; its tests are opt-in | `BABARIFY_TEST_MPV=1 pytest -k mpv` |
| R8 | M2 | Bad file briefly showed PLAYING | libVLC fires *Playing* before it knows the file is readable | Hold LOADING until confirmed by length, position or video output | `test_invalid_media_fails_without_playing_and_engine_recovers` (asserts no PLAYING) |
| R9 | M2 | Play/seek after end did nothing | An ended libVLC 3 player ignores `play()` | Restart with `stop()` + `play()`; seek-after-end pauses at target | `test_end_then_play_restarts`, `test_seek_after_end_pauses_at_target` |
| R10 | M2 | No codec/size for TS, PS and Ogg | Streams and video size arrive after *Playing* | Refresh media info on stream/vout events; retry while size unknown | Corpus test on `c_h264_ac3_720p.ts`, `c_mpeg2_mp2_576p.mpg`, `c_theora_vorbis_480p.ogv`, `e_interlaced_mpeg2_1080i.ts` |
| R11 | M2 | Raw fourccs (`mp4v`, `VP80`, …) | No mapping | Map to FFmpeg names | Corpus test (codec equality for 30+ files) |
| R12 | M2 | Position stuck after seeking while paused | libVLC sends no TimeChanged while paused | Report the accepted target | `test_controls_play_pause_seek_volume_rate` |
| R13 | M2 | Double-click on video ignored | libVLC's video window captured mouse/keys | `video_set_mouse_input(False)`, `video_set_key_input(False)` | `tools/real_input_check.py` (sends real input; run manually) |
| R14 | M2 | "4 Could not open…" in error text | libVLC log level prefix kept | Prefix stripped | `test_invalid_media_fails_without_playing_and_engine_recovers` |
| R15 | M2 | Error page overwritten by file title | Synchronous failure inside `open()` | Window updated before opening | `test_open_failure_shows_error_page` |
| R16 | M2 | Evidence screenshot captured another app | Screen grab of a covered window | Stay-on-top + ownership check before saving | `tools/player_screenshot.py` refuses to save (process control, not a test) |
| R17 | M3 | Status showed "decoder: none reported" while hardware decoding | Decoder logged after *Playing* | Status refreshed each second while playing | Screenshot evidence; `test_decoder_is_reported_once_decoding` covers the data source |
| R18 | M4 | Hardware decoding "Off" still used the GPU | libVLC 3.0.24 ignores `--avcodec-hw` at instance level | Per-media `:avcodec-hw=` option | `test_hardware_decoding_off_reports_software`; `tools/engine-benchmark/hw_decode_check.py` |
| R19 | M3 | Large window resize blocks the UI ~100–125 ms at 4K / 250 % | Qt layout + paint of the whole widget tree at high DPI; no single dominant part (M4 breakdown) | **Open** — see M4 report §4 | `tools/ui_responsiveness.py`, `tools/resize_probe.py` |
| R20 | M2/M4 | Handles and memory grew per engine; after ~100 engines in one process `libvlc_new` crashed (access violation) | Every libVLC 3.0.24 instance create/release leaks ~15 handles and ~0.5 MB (reproduced with bare libVLC, no Babarify code) | One shared libVLC instance per process; engines own only player and media | `test_repeated_engine_create_close` (run with `BABARIFY_ENGINE_CYCLES=50`), full default suite (~150 engines per process) |
| R21 | M4 | Seek right after pause left the position display at the old time | The pause had not taken effect yet; paused libVLC sends no TimeChanged | Always report the accepted seek target | `test_seek_immediately_after_pause_reports_target`, `test_seek_storm` (300 seeks, real resumption) |
