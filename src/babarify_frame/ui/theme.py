"""Babarify dark theme: deep navy surfaces, blue/cyan highlights, green accents.

M2 keeps styling minimal and functional; the premium visual design is M3.
"""

from __future__ import annotations

BG = "#070B15"
SURFACE = "#0E1628"
SURFACE_RAISED = "#16213A"
BORDER = "#22304D"
TEXT = "#E6EDF7"
TEXT_MUTED = "#8A9AB5"
BLUE = "#3B82F6"
CYAN = "#22D3EE"
GREEN = "#22C55E"
AMBER = "#F59E0B"
RED = "#F87171"

STYLESHEET = f"""
QMainWindow, QWidget#root {{ background: {BG}; color: {TEXT}; }}
QWidget {{ color: {TEXT}; font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; }}
QMenuBar {{ background: {BG}; color: {TEXT}; }}
QMenuBar::item:selected {{ background: {SURFACE_RAISED}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {SURFACE_RAISED}; }}
QMenu::item:disabled {{ color: {TEXT_MUTED}; }}
QWidget#header {{ background: {BG}; }}
QLabel#productName {{ font-size: 14pt; font-weight: 600; }}
QLabel#brand {{ color: {CYAN}; font-size: 8pt; font-weight: 600; letter-spacing: 2px; }}
QLabel#tagline {{ color: {TEXT_MUTED}; }}
QFrame#messagePage {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE}, stop:1 {BG});
}}
QLabel#messageTitle {{ font-size: 15pt; font-weight: 600; }}
QLabel#messageBody {{ color: {TEXT_MUTED}; }}
QFrame#controlBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
QLabel#timeLabel {{ color: {TEXT_MUTED}; font-family: "Cascadia Mono", "Consolas", monospace; }}
QToolButton {{ border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: {SURFACE_RAISED}; }}
QToolButton:disabled {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {BLUE}, stop:1 {CYAN}); border-radius: 2px;
}}
QSlider::sub-page:horizontal:disabled {{ background: {BORDER}; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QSlider::handle:horizontal:disabled {{ background: {TEXT_MUTED}; }}
QStatusBar {{ background: {BG}; color: {TEXT_MUTED}; }}
"""
