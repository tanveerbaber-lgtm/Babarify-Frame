"""Accessibility audit (M11): names, keyboard focus and colour contrast, for every page and dialog.

* Names: every interactive control (button, check box, slider, combo box, text field, list,
  spin box, tab bar) needs a name a screen reader can announce: its accessible name, its own
  text, or a QFormLayout/QLabel buddy label.
* Keyboard: controls in dialogs must take focus (Tab). The player's control bar is excluded by
  design (its buttons are mouse targets; every action has a key and a menu entry).
* Contrast (WCAG 2.1): text colours of the theme against the backgrounds they are used on;
  4.5:1 for normal text, 3:1 for large text and for focus indicators.
Uses the mock engine; nothing is played. Writes JSON (default: stdout summary only).
Usage:  python tools/a11y_audit.py [out.json]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListView,
    QScrollBar,
    QTabBar,
    QTextBrowser,
    QWidget,
)

INTERACTIVE = (
    QAbstractButton,
    QAbstractSlider,
    QComboBox,
    QLineEdit,
    QListView,
    QAbstractSpinBox,
    QTabBar,
    QTextBrowser,
)


def luminance(hex_colour: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def form_label_for(widget: QWidget) -> str:
    parent = widget.parentWidget()
    while parent is not None:
        layout = parent.layout()
        for form in [layout] if isinstance(layout, QFormLayout) else parent.findChildren(QFormLayout):
            label = form.labelForField(widget)
            if isinstance(label, QLabel) and label.text():
                return label.text()
        parent = parent.parentWidget()
    for label in widget.window().findChildren(QLabel):
        if label.buddy() is widget and label.text():
            return label.text()
    return ""


def name_of(widget: QWidget) -> str:
    if widget.accessibleName():
        return widget.accessibleName()
    text = getattr(widget, "text", None)
    if callable(text) and isinstance(widget, QAbstractButton) and text().strip():
        return str(text())
    return form_label_for(widget)


def describe(widget: QWidget) -> str:
    chain, w = [], widget
    while w is not None and len(chain) < 4:
        chain.append(w.objectName() or type(w).__name__)
        w = w.parentWidget()
    tip = widget.toolTip()
    return " < ".join(chain) + (f" (tooltip: {tip[:40]})" if tip else "")


def audit_widget(root: QWidget, where: str, dialog: bool) -> list[dict[str, str]]:
    problems = []
    for widget in [root, *root.findChildren(QWidget)]:
        if not isinstance(widget, INTERACTIVE) or not widget.isVisibleTo(root):
            continue
        # Parts Qt names itself: scroll bars, the text field inside a (named) spin box, tab bars
        # (each tab's text is announced), tab scroll buttons.
        parent = widget.parentWidget()
        if (
            isinstance(widget, (QScrollBar, QTabBar))
            or isinstance(parent, QAbstractSpinBox)
            or widget.objectName() == "qt_tabwidget_scrollbutton"
        ):
            continue
        if not name_of(widget):
            problems.append({"where": where, "issue": "no accessible name", "widget": describe(widget)})
        if dialog and widget.focusPolicy().value == 0:  # Qt.NoFocus
            problems.append(
                {"where": where, "issue": "cannot be reached with the keyboard", "widget": describe(widget)}
            )
    return problems


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    config = Path(tempfile.mkdtemp(prefix="babarify-a11y-"))
    os.environ["BABARIFY_CONFIG_DIR"] = str(config)
    os.environ["BABARIFY_LOG_DIR"] = str(config / "logs")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from babarify_frame.configuration.preferences import Preferences, PreferencesStore
    from babarify_frame.core.models import PlaybackState as S
    from babarify_frame.playback.adapters.mock import MockEngine
    from babarify_frame.playback.factory import EngineDescriptor, EngineFactory, EngineProbe
    from babarify_frame.ui import theme
    from babarify_frame.ui.app import load_icon
    from babarify_frame.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.STYLESHEET)
    factory = EngineFactory()
    factory.register(EngineDescriptor("mock", "Mock", MockEngine, lambda: EngineProbe("mock", True, "1")))
    store = PreferencesStore(config / "settings.json")
    store.save(Preferences(ai_enabled=True))
    window = MainWindow(factory, load_icon(), engine_name="mock", store=store)
    window.resize(1180, 740)
    window.show()
    window.start_engine()
    while not window.player.engine_is_ready:
        app.processEvents()
    media = config / "film.mp4"
    media.write_bytes(b"\x00")
    window.open_path(str(media))
    while window.player.state is not S.PLAYING:
        app.processEvents()

    problems: list[dict[str, str]] = []
    for page in (window.home, window.library, window.player, window.settings):
        window.show_page(page)
        app.processEvents()
        problems += audit_widget(page, type(page).__name__, dialog=False)
    problems += audit_widget(window, "window (rail)", dialog=False)
    dialogs: list[tuple[str, QDialog | None]] = [
        ("Sync and delay", window.player.show_sync_dialog()),
        ("Picture & Sound", window.show_enhancements()),
        ("Playback info", window.show_playback_info()),
        ("Media information", window.show_media_info()),
        ("Bookmarks", window.show_bookmarks()),
        ("Open network stream", window.choose_stream()),
        ("Generate subtitles", window.show_generate_subtitles()),
        ("Search spoken words", window.show_spoken_search()),
    ]
    enhancements = window.show_enhancements()
    for name, dialog in dialogs:
        if dialog is None:
            problems.append({"where": name, "issue": "dialog did not open", "widget": ""})
            continue
        app.processEvents()
        if dialog is enhancements:
            for i in range(enhancements.tabs.count()):
                enhancements.tabs.setCurrentIndex(i)
                app.processEvents()
                problems += audit_widget(dialog, f"{name} / {enhancements.tabs.tabText(i)}", dialog=True)
        else:
            problems += audit_widget(dialog, name, dialog=True)
        dialog.close()

    pairs = {
        "text on page": (theme.TEXT, theme.BG),
        "text on panel": (theme.TEXT, theme.SURFACE),
        "text on raised card": (theme.TEXT, theme.SURFACE_RAISED),
        "muted text on page": (theme.TEXT_MUTED, theme.BG),
        "muted text on panel": (theme.TEXT_MUTED, theme.SURFACE),
        "muted text on raised card": (theme.TEXT_MUTED, theme.SURFACE_RAISED),
        "cyan accent on page": (theme.CYAN, theme.BG),
        "amber warning on panel": (theme.AMBER, theme.SURFACE),
        "red error on page": (theme.RED, theme.BG),
        "green on panel": (theme.GREEN, theme.SURFACE),
        "play icon on blue": ("#04101F", theme.BLUE),
        "focus ring (cyan) vs panel": (theme.CYAN, theme.SURFACE),
        "control border vs page (non-text)": (theme.CONTROL_BORDER, theme.BG),
        "control border vs panel (non-text)": (theme.CONTROL_BORDER, theme.SURFACE),
        "control border vs raised fill (non-text)": (theme.CONTROL_BORDER, theme.SURFACE_RAISED),
    }
    contrasts = {name: contrast(fg, bg) for name, (fg, bg) in pairs.items()}
    window.close()
    report = {"problems": problems, "contrast": contrasts}
    for p in problems:
        print(f"[{p['where']}] {p['issue']}: {p['widget']}")
    print(f"{len(problems)} problems")
    for name, ratio in contrasts.items():
        need = 3.0 if "focus" in name or "non-text" in name else 4.5
        print(f"{'OK  ' if ratio >= need else 'LOW '} {ratio:5.2f}  {name} (needs {need})")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
