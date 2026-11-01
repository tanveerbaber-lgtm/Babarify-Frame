"""Capture M9 evidence: AI settings, the generate dialog after a real run, machine-generated
subtitles on the video, and spoken-word search.

Real libVLC and the real worker (base model from BABARIFY_MODELS_DIR, default .models), on
speech synthesised on this PC. The player is captured from the screen after the ownership
check (R16); dialogs and the Settings page with QWidget.grab(). Throw-away settings.
Usage:  python tools/ai_screenshot.py docs/milestones/M9/evidence
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_speech import make_speech
from player_screenshot import grab, pump, wait

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    config = Path(tempfile.mkdtemp(prefix="babarify-m9-shots-"))
    os.environ["BABARIFY_CONFIG_DIR"] = str(config)
    os.environ.setdefault("BABARIFY_MODELS_DIR", str(ROOT / ".models"))
    _wav, video = make_speech(config / "media")
    assert video is not None, "ffmpeg is needed for the evidence video"
    from babarify_frame.configuration.preferences import Preferences, PreferencesStore
    from babarify_frame.core.models import PlaybackState as S
    from babarify_frame.playback.factory import default_factory
    from babarify_frame.ui.app import load_icon
    from babarify_frame.ui.main_window import MainWindow
    from babarify_frame.ui.theme import STYLESHEET

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    store = PreferencesStore(config / "settings.json")
    store.save(Preferences(ai_enabled=True, ai_model="base"))
    window = MainWindow(default_factory(), load_icon(), store=store)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.resize(1180, 740)
    window.show()
    window.start_engine()
    wait(app, window, S.READY)
    window.open_path(str(video))
    wait(app, window, S.PLAYING)
    pump(app, 0.5)
    window.player.toggle_play_pause()

    dialog = window.show_generate_subtitles()
    assert dialog is not None
    dialog.resize(560, 360)
    pump(app, 0.3)
    dialog.grab().save(str(out / "generate_dialog.png"))
    dialog.start_button.click()
    for _ in range(600):
        pump(app, 0.2)
        if not window.subtitle_job.running:
            break
    pump(app, 0.5)
    dialog.grab().save(str(out / "generate_done.png"))
    print("status:", dialog.status.text())
    dialog.hide()

    window.player.seek_to(8_000)
    window.player.toggle_play_pause()
    pump(app, 1.2)
    window.player.toggle_play_pause()
    pump(app, 0.6)
    grab(app, window, out / "machine_subtitles.png")

    search = window.show_spoken_search()
    assert search is not None
    search.query.setText("boats")
    search.resize(620, 360)
    pump(app, 0.3)
    search.grab().save(str(out / "spoken_search.png"))
    print("results:", search.results.count())
    search.hide()

    window.show_page(window.settings)
    pump(app, 0.3)
    card = window.settings.ai_enabled.parentWidget()
    assert card is not None
    card.grab().save(str(out / "settings_ai.png"))
    window.close()
    for name in ("generate_dialog", "generate_done", "machine_subtitles", "spoken_search", "settings_ai"):
        print(name, (out / f"{name}.png").exists())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
