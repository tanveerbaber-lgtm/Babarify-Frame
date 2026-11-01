"""Capture M8 evidence: seek-bar preview with chapter and bookmark marks, and the M8 dialogs.

Uses real libVLC and a chapter test clip generated with ffmpeg. The player (Direct3D video and
the preview popup) is captured from the screen after the ownership check (R16); the hover point
is placed away from the check's sample points. Dialogs are rendered with QWidget.grab().
A local HTTP server (127.0.0.1) provides the refused-redirect example. Throw-away settings.
Usage:  python tools/advanced_media_screenshot.py docs/milestones/M8/evidence
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from babarify_frame.configuration.preferences import PreferencesStore
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.ui.main_window import MainWindow
from netserver import LocalServer
from player_screenshot import grab, pump, wait

ROOT = Path(__file__).resolve().parents[1]


def make_clip(folder: Path) -> Path:
    meta = folder / "meta.txt"
    chapters = "".join(
        f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start}\nEND={end}\ntitle={title}\n"
        for start, end, title in (
            (0, 20_000, "Opening titles"),
            (20_000, 45_000, "The harbour"),
            (45_000, 75_000, "Night market"),
            (75_000, 90_000, "Credits"),
        )
    )
    meta.write_text(f";FFMETADATA1\ntitle=Harbour Lights\nartist=Babarify test\n{chapters}", encoding="utf-8")
    clip = folder / "harbour_lights.mkv"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=90",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=90:sample_rate=48000", "-i", str(meta),
         "-map_metadata", "2", "-map_chapters", "2", "-c:v", "libx264", "-preset", "veryfast",
         "-g", "25", "-c:a", "aac", "-ac", "2", str(clip)],
        check=True,
    )  # fmt: skip
    return clip


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    config = Path(tempfile.mkdtemp(prefix="babarify-m8-shots-"))
    os.environ["BABARIFY_CONFIG_DIR"] = str(config)
    clip = make_clip(config)
    from babarify_frame.playback.factory import default_factory
    from babarify_frame.ui.app import libvlc_preview, load_icon
    from babarify_frame.ui.theme import STYLESHEET

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(
        default_factory(),
        load_icon(),
        store=PreferencesStore(config / "settings.json"),
        preview_factory=libvlc_preview,
    )
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.resize(1180, 740)
    window.show()
    window.start_engine()
    wait(app, window, S.READY)
    window.open_path(str(clip))
    wait(app, window, S.PLAYING)
    pump(app, 1.0)
    player = window.player
    for seconds, label in ((12, "Logo"), (52, "Lanterns"), (61, "")):
        player.seek_to(seconds * 1000)
        pump(app, 0.4)
        player.add_bookmark(label)
    player.seek_to(30_000)
    pump(app, 1.0)
    player.toggle_play_pause()
    pump(app, 0.6)

    seek = player.controls.seek
    hover_ms = 57_000  # inside "Night market"; about 30 % across the window, away from check points
    anchor = seek.mapToGlobal(QPoint(seek.x_of(hover_ms), 0))
    seek.hovered.emit(hover_ms, anchor)
    for _ in range(40):
        pump(app, 0.1)
        if player._popup.image.isVisible():
            break
        seek.hovered.emit(hover_ms, anchor)
    pump(app, 0.3)
    grab(app, window, out / "seek_preview.png")
    seek.hover_left.emit()

    info = window.show_media_info()
    info.resize(560, 700)
    pump(app, 0.3)
    info.grab().save(str(out / "media_info.png"))
    info.hide()

    marks = window.show_bookmarks()
    marks.resize(420, 360)
    pump(app, 0.3)
    marks.grab().save(str(out / "bookmarks.png"))
    marks.hide()

    window._fill_chapters_menu()
    print("chapters menu:", [a.text() for a in window.chapters_menu.actions()])

    dialog = window.choose_stream()
    assert dialog is not None
    dialog.address.setText("file:///C:/Users/Public/secret.mkv")
    pump(app, 0.2)
    dialog.grab().save(str(out / "stream_dialog_refused.png"))
    dialog.address.setText("https://example.com/live/stream.m3u8?token=abc123")
    pump(app, 0.2)
    dialog.grab().save(str(out / "stream_dialog_ok.png"))
    dialog.reject()

    server = LocalServer(config)
    target = quote(clip.as_uri(), safe="")
    window.open_path(server.url(f"redirect?to={target}"))
    wait(app, window, S.ERROR)
    pump(app, 0.5)
    window.grab().save(str(out / "redirect_refused.png"))
    print("message:", player.message)
    server.close()
    window.close()
    for name in (
        "seek_preview",
        "media_info",
        "bookmarks",
        "stream_dialog_refused",
        "stream_dialog_ok",
        "redirect_refused",
    ):
        print(name, (out / f"{name}.png").exists())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
