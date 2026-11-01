"""Capture M7 evidence: the player with picture adjustments, and each Picture & Sound tab.

The player is captured from the screen (Direct3D video) after the ownership check (R16); the
panel's tabs are pure Qt widgets and are rendered with QWidget.grab(), so a window on top of
them cannot leak into the image. Uses throw-away settings.
Usage:  python tools/enhancements_screenshot.py docs/milestones/M7/evidence
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.ui.main_window import MainWindow
from player_screenshot import MEDIA, grab, pump, wait


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    config = Path(tempfile.mkdtemp(prefix="babarify-m7-shots-"))
    os.environ["BABARIFY_CONFIG_DIR"] = str(config)
    os.environ["BABARIFY_SNAPSHOT_DIR"] = str(config / "snapshots")
    from babarify_frame.playback.factory import default_factory
    from babarify_frame.ui.app import load_icon
    from babarify_frame.ui.theme import STYLESHEET

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(default_factory(), load_icon(), store=PreferencesStore(config / "settings.json"))
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.resize(1180, 740)
    window.show()
    window.start_engine()
    wait(app, window, S.READY)
    window.open_path(str(MEDIA / "h264_1080p30_aac.mp4"))
    wait(app, window, S.PLAYING)
    pump(app, 1.5)
    window.player.toggle_play_pause()
    pump(app, 0.5)
    grab(app, window, out / "picture_normal.png")

    panel = window.show_enhancements()
    panel.picture_sliders["saturation"].setValue(30)
    panel.picture_sliders["brightness"].setValue(120)
    panel.hide()
    window.player.toggle_play_pause()
    pump(app, 0.4)
    window.player.toggle_play_pause()
    pump(app, 0.5)
    grab(app, window, out / "picture_adjusted.png")

    panel.aspect.setCurrentIndex(panel.aspect.findData("4:3"))
    window.player.toggle_play_pause()
    pump(app, 0.4)
    window.player.toggle_play_pause()
    pump(app, 0.5)
    grab(app, window, out / "aspect_4x3.png")

    panel.show()
    panel.resize(640, 560)
    panel.eq_preset.setCurrentIndex(panel.eq_preset.findText("Rock"))
    panel.eq_preset.activated.emit(panel.eq_preset.currentIndex())
    panel.save_profile("Night viewing")
    for index, name in enumerate(("panel_picture", "panel_video", "panel_audio", "panel_profiles")):
        panel.tabs.setCurrentIndex(index)
        pump(app, 0.3)
        image = panel.grab()
        image.save(str(out / f"{name}.png"))
        print(f"saved {out / name}.png ({image.width()}x{image.height()})")

    path = window.player.take_snapshot()
    pump(app, 1.0)
    print(f"snapshot: {path} exists={path is not None and path.exists()}")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
