"""Transcription worker process (M9): ``python -m babarify_frame.ai.worker``.

Runs apart from the player so that the speech engine (CTranslate2, onnxruntime) cannot take
playback down, and at below-normal priority with half the processor cores. Steps:
1. libVLC transcodes the file's audio to 16 kHz mono WAV in a temporary folder (no second
   media parser: the file is read by the same engine that plays it).
2. faster-whisper recognises speech (voice-activity filter on, word timings), from the model
   folder only (offline: ``HF_HUB_OFFLINE``).
3. Cues are written as SRT, plus a JSON list for the spoken-word index.
Progress goes to stdout as JSON lines: {"stage": ...}, {"progress": 0..1}, {"language": ...},
{"done": {...}} or {"error": "..."}. Exit code 0 on success.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

SAMPLE_RATE = 16_000
EXTRACT_TIMEOUT_S = 600.0


def emit(**message: Any) -> None:
    print(json.dumps(message), flush=True)


def lower_priority() -> None:
    if sys.platform == "win32":
        from ctypes import wintypes

        below_normal = 0x00004000
        kernel32 = ctypes.windll.kernel32
        # Declared types matter: without them the process pseudo-handle (-1) is passed as a 32-bit
        # int on 64-bit Windows, and the call fails silently (found by the M9 priority test).
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), below_normal):
            emit(warning="could not lower the process priority")


def extract_audio(media: str, out: Path) -> float:
    """Decode the first audio track to 16 kHz mono 16-bit WAV with libVLC; returns seconds."""
    from babarify_frame.playback.adapters.libvlc import _load_vlc

    vlc = _load_vlc()
    instance = vlc.Instance(["--no-video-title-show", "--no-lua", "--no-video", "--no-spu", "--quiet"])
    item = instance.media_new_path(media)
    dst = str(out).replace("\\", "/").replace("'", "")
    item.add_option(
        ":sout=#transcode{vcodec=none,scodec=none,acodec=s16l,channels=1,"
        f"samplerate={SAMPLE_RATE}}}:std{{access=file,mux=wav,dst='{dst}'}}"
    )
    item.add_option(":sout-keep")
    item.add_option(":no-sout-all")  # first audio track only
    player = instance.media_player_new()
    player.set_media(item)
    started = time.monotonic()
    player.play()
    done = (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped)
    while player.get_state() not in done:
        if time.monotonic() - started > EXTRACT_TIMEOUT_S:
            raise RuntimeError("reading the audio took too long")
        time.sleep(0.05)
    failed = player.get_state() is vlc.State.Error
    player.stop()
    player.release()
    item.release()
    if failed or not out.is_file() or out.stat().st_size <= 44:
        raise RuntimeError("the file has no audio that could be read")
    with wave.open(str(out)) as w:
        return float(w.getnframes() / w.getframerate())


def transcribe(audio_path: Path, model_dir: str, language: str | None, threads: int) -> dict[str, Any]:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    import numpy as np
    from faster_whisper import WhisperModel

    from babarify_frame.ai.subtitles import Word, build_cues

    with wave.open(str(audio_path)) as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    audio = samples.astype(np.float32) / 32768.0
    duration = max(0.001, len(audio) / SAMPLE_RATE)
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=threads)
    segments, info = model.transcribe(
        audio, language=language, vad_filter=True, beam_size=5, word_timestamps=True
    )
    emit(language=info.language, probability=round(info.language_probability, 3))
    words: list[Word] = []
    for segment in segments:
        for w in segment.words or []:
            words.append(Word(round(w.start * 1000), round(w.end * 1000), w.word))
        emit(progress=round(min(1.0, segment.end / duration), 3))
    return {"language": info.language, "words": words, "cues": build_cues(words)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="babarify_frame.ai.worker")
    parser.add_argument("--media", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--srt", required=True)
    parser.add_argument("--cues", required=True)
    args = parser.parse_args(argv)
    lower_priority()
    threads = max(1, (os.cpu_count() or 2) // 2)
    try:
        from babarify_frame.ai.subtitles import to_srt

        with tempfile.TemporaryDirectory(prefix="babarify-ai-") as tmp:
            emit(stage="audio")
            wav = Path(tmp) / "audio.wav"
            seconds = extract_audio(args.media, wav)
            emit(stage="speech", seconds=round(seconds, 1))
            language = None if args.language == "auto" else args.language
            result = transcribe(wav, args.model_dir, language, threads)
        cues = result["cues"]
        srt, cues_out = Path(args.srt), Path(args.cues)
        srt.parent.mkdir(parents=True, exist_ok=True)
        srt.write_text(to_srt(cues), encoding="utf-8")
        cues_out.write_text(
            json.dumps([[c.start_ms, c.end_ms, c.text] for c in cues], ensure_ascii=False), encoding="utf-8"
        )
        emit(done={"cues": len(cues), "language": result["language"], "srt": str(srt)})
        return 0
    except Exception as exc:  # reported to the app; the process ends either way
        emit(error=f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
