"""babarify-ai-worker.exe: the local transcription worker (console program, started hidden)."""

import sys

from babarify_frame.ai.worker import main

sys.exit(main())
