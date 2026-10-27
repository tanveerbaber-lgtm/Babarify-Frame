"""Babarify dark theme: deep navy surfaces, blue/cyan highlights, green accents."""

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
QLabel#productName {{ font-size: 18pt; font-weight: 600; }}
QLabel#brand {{ color: {CYAN}; font-size: 9pt; font-weight: 600; letter-spacing: 2px; }}
QLabel#tagline {{ color: {TEXT_MUTED}; }}
QFrame#videoArea {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE}, stop:1 {BG});
    border: 1px solid {BORDER}; border-radius: 14px;
}}
QLabel#emptyTitle {{ font-size: 15pt; font-weight: 600; }}
QLabel#emptyBody {{ color: {TEXT_MUTED}; }}
QFrame#enginePanel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QLabel#panelTitle {{ color: {TEXT_MUTED}; font-size: 9pt; font-weight: 600; letter-spacing: 1px; }}
QStatusBar {{ background: {BG}; color: {TEXT_MUTED}; }}
"""
