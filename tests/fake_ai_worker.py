"""Stand-in for babarify_frame.ai.worker in UI tests: same arguments, same JSON-line protocol.

Behaviour follows the media file name: "nospeech" → no cues, "fail" → an error, "slow" → waits
(to be cancelled), "crash" → exits without a result; otherwise three cues are written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def emit(**message: object) -> None:
    print(json.dumps(message), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("--media", "--model-dir", "--language", "--srt", "--cues"):
        parser.add_argument(name)
    args = parser.parse_args()
    name = Path(args.media).name
    emit(stage="audio")
    emit(stage="speech", seconds=60)
    if "crash" in name:
        return 3
    if "fail" in name:
        emit(error="RuntimeError: the file has no audio that could be read")
        return 1
    if "slow" in name:
        emit(progress=0.1)
        time.sleep(60)
    cues = [] if "nospeech" in name else [
        [2_670, 6_270, "The harbor lights came on one by one."],
        [7_190, 11_170, "Maria counted seven boats."],
        [11_870, 15_650, "The wind had turned cold."],
    ]  # fmt: skip
    for fraction in (0.3, 0.6, 1.0):
        emit(progress=fraction)
    Path(args.srt).write_text(
        "".join(f"{i}\n00:00:0{i},000 --> 00:00:0{i},900\n{c[2]}\n\n" for i, c in enumerate(cues, 1)),
        encoding="utf-8",
    )
    Path(args.cues).write_text(json.dumps(cues), encoding="utf-8")
    language = "en" if args.language in (None, "auto") else args.language
    emit(done={"cues": len(cues), "language": language, "srt": args.srt})
    return 0


if __name__ == "__main__":
    sys.exit(main())
