"""Optional, local-only AI features (M9): speech-to-text subtitles and spoken-word search.

Rules (plan §8, M9):
* Off until the user switches it on (Settings → AI features).
* Everything runs on this PC. Media, audio and subtitles are never uploaded. The only network
  use is downloading a speech model, which the user starts after seeing its size and source.
* Model files are pinned to a revision and checked against known SHA-256 hashes.
* Transcription runs in a separate, lower-priority process (``ai.worker``), so a failure or the
  memory it needs cannot affect playback; cancelling ends that process.
* Generated subtitles are labelled machine-generated (file name and UI) and kept in the app's
  own folder, never next to the user's files. They can be deleted at any time.
"""
