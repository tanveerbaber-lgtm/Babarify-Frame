"""Babarify design tokens and the application stylesheet.

Dark, premium surfaces; blue -> cyan for interactive accents; green for "on/active"
confirmation. Every colour, spacing step, radius and type size used by the UI is defined
here so the look stays consistent (M3 acceptance: branding and spacing consistency).

Colour themes replace the colours below (``apply_theme``), so code reads them as ``theme.BG`` when it
draws, rather than keeping a copy, and text colours stay the same so every theme reads alike.
"""

from __future__ import annotations

from babarify_frame.core.themes import DEFAULT_THEME, THEMES

# Colour
BG = "#070B15"  # window background
SURFACE = "#0E1628"  # panels, control bar
SURFACE_RAISED = "#16213A"  # hover, cards
SURFACE_PRESSED = "#1E2B48"
BORDER = "#22304D"  # decorative edges (cards, menus, separators)
# Edges that identify a control (WCAG 2.1 1.4.11: at least 3:1 against every surface; M11 review).
CONTROL_BORDER = "#5E7096"
TEXT = "#E6EDF7"
TEXT_MUTED = "#8A9AB5"
TEXT_DISABLED = "#4A5875"
BLUE = "#3B82F6"
CYAN = "#22D3EE"
GREEN = "#22C55E"
AMBER = "#F59E0B"
RED = "#F87171"
ON_ACCENT = "#04101F"  # icons and text on accent-coloured buttons

# Spacing scale (px)
XS, S, M, L, XL, XXL = 4, 8, 12, 16, 24, 32

# Corner radius (px)
RADIUS_S, RADIUS_M, RADIUS_L = 6, 10, 16

# Type scale (pt)
FONT_CAPTION, FONT_BODY, FONT_SUBTITLE, FONT_TITLE, FONT_DISPLAY = 9, 10, 12, 15, 24

# Arial for body text and Arial Bold for titles and headings. Its digits are all one width, so times
# don't jump about as they count.
FONT_FAMILY = "Arial"
FONT_STACK = f'"{FONT_FAMILY}", sans-serif'


def _accent_gradient() -> str:
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {BLUE}, stop:1 {CYAN})"


def build_stylesheet() -> str:
    accent_gradient = _accent_gradient()
    return f"""
* {{ font-family: {FONT_STACK}; font-size: {FONT_BODY}pt; color: {TEXT}; }}
QMainWindow, QWidget#root, QDialog {{ background: {BG}; }}
QTabWidget > QWidget, QTabWidget QStackedWidget > QWidget {{ background: {BG}; }}
QToolTip {{
    background: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER};
    padding: {XS}px {S}px; border-radius: {RADIUS_S}px;
}}

/* Menus */
QMenuBar {{ background: {BG}; padding: 2px {XS}px; }}
QMenuBar::item {{ padding: {XS}px {M}px; border-radius: {RADIUS_S}px; }}
QMenuBar::item:selected {{ background: {SURFACE_RAISED}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: {XS}px; border-radius: {RADIUS_S}px; }}
QMenu::item {{ padding: {S - 2}px {XL}px {S - 2}px {M}px; border-radius: {RADIUS_S}px; }}
QMenu::item:selected {{ background: {SURFACE_RAISED}; }}
QMenu::item:disabled {{ color: {TEXT_DISABLED}; }}
QMenu::item:checked {{ color: {CYAN}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: {XS}px {S}px; }}

/* Navigation rail */
QFrame#navRail {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
QToolButton#navButton {{
    border: none; border-radius: {RADIUS_M}px; padding: {S}px; margin: 2px {S}px;
    color: {TEXT_MUTED}; font-size: {FONT_CAPTION}pt;
}}
QToolButton#navButton:hover {{ background: {SURFACE_RAISED}; color: {TEXT}; }}
QToolButton#navButton:checked {{ background: {SURFACE_PRESSED}; color: {TEXT}; border-left: 3px solid {CYAN}; }}
QToolButton#navButton:disabled {{ color: {TEXT_DISABLED}; }}

/* Typography roles */
QLabel#display {{ font-size: {FONT_DISPLAY}pt; font-weight: 700; }}
QLabel#title {{ font-size: {FONT_TITLE}pt; font-weight: 700; }}
QLabel#subtitle {{ font-size: {FONT_SUBTITLE}pt; font-weight: 700; }}
QLabel#muted {{ color: {TEXT_MUTED}; }}
QLabel#caption {{ color: {TEXT_MUTED}; font-size: {FONT_CAPTION}pt; }}
QLabel#warning {{ color: {AMBER}; }}
QLabel#tagline {{ color: {TEXT_MUTED}; font-size: {FONT_SUBTITLE}pt; }}
QLabel#errorIcon {{ color: {RED}; }}
QLabel#time {{ color: {TEXT_MUTED}; font-size: {FONT_CAPTION}pt; }}
QLabel#mediaTitle {{ font-weight: 700; }}
QLabel#kbd {{
    background: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 1px {S - 2}px; font-size: {FONT_CAPTION}pt;
}}

/* Pages */
QWidget#page {{ background: {BG}; }}
QFrame#dropZone {{
    background: {SURFACE}; border: 1px dashed {BORDER}; border-radius: {RADIUS_L}px;
}}
QFrame#dropZone[dragActive="true"] {{ border: 2px dashed {CYAN}; background: {SURFACE_RAISED}; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS_M}px; }}
QFrame#messagePage {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE}, stop:1 {BG});
}}

/* Buttons */
QPushButton {{
    background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER}; border-radius: {RADIUS_M}px;
    padding: {S}px {L}px;
}}
QPushButton:hover {{ background: {SURFACE_PRESSED}; }}
QPushButton:disabled {{ color: {TEXT_DISABLED}; }}
QPushButton#primary {{
    background: {accent_gradient}; border: none; color: {ON_ACCENT}; font-weight: 700;
    padding: {M}px {XL}px; font-size: {FONT_SUBTITLE}pt;
}}
QPushButton#primary:hover {{ background: {CYAN}; }}
QToolButton {{ border: none; border-radius: {RADIUS_S}px; padding: {XS}px; }}
QToolButton:hover {{ background: {SURFACE_RAISED}; }}
QToolButton:pressed {{ background: {SURFACE_PRESSED}; }}
QToolButton:disabled {{ background: transparent; }}
QToolButton#playButton {{ background: {accent_gradient}; border-radius: 20px; }}
QToolButton#playButton:hover {{ background: {CYAN}; }}
QToolButton#playButton:disabled {{ background: {SURFACE_RAISED}; }}
QToolButton#speedButton {{ font-size: {FONT_CAPTION}pt; padding: {XS}px {S}px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* Keyboard focus is always visible */
QPushButton:focus, QToolButton:focus, QComboBox:focus, QCheckBox:focus, QSpinBox:focus {{
    outline: none; border: 2px solid {CYAN};
}}

/* Control bar */
QFrame#controlBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}

/* Sliders */
QSlider::groove:horizontal {{ height: 4px; background: {CONTROL_BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent_gradient}; border-radius: 2px; }}
QSlider::sub-page:horizontal:disabled {{ background: {BORDER}; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QSlider::handle:horizontal:hover {{ background: {CYAN}; }}
QSlider::handle:horizontal:disabled {{ background: {TEXT_DISABLED}; }}
QSlider#seek::groove:horizontal {{ height: 5px; }}
QSlider[boost="true"]::sub-page:horizontal {{ background: {AMBER}; }}
QSlider::groove:vertical {{ width: 4px; background: {CONTROL_BORDER}; border-radius: 2px; }}
QSlider::add-page:vertical {{ background: {accent_gradient}; border-radius: 2px; }}
QSlider::add-page:vertical:disabled {{ background: {BORDER}; }}
QSlider::handle:vertical {{ background: {TEXT}; height: 12px; margin: 0 -5px; border-radius: 6px; }}
QSlider::handle:vertical:disabled {{ background: {TEXT_DISABLED}; }}
QSlider::sub-page:horizontal:disabled {{ background: {BORDER}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: {RADIUS_S}px; top: -1px; }}

/* Settings form */
QComboBox, QSpinBox {{
    background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER}; border-radius: {RADIUS_S}px;
    padding: {XS}px {S}px; min-width: 120px;
}}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {SURFACE_PRESSED}; }}
QCheckBox {{ spacing: {S}px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {CONTROL_BORDER}; background: {SURFACE_RAISED}; }}
QCheckBox::indicator:checked {{ background: {GREEN}; border-color: {GREEN}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {CONTROL_BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {CONTROL_BORDER}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

/* Library and history (M6) */
QLineEdit {{
    background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER}; border-radius: {RADIUS_S}px;
    padding: {XS}px {S}px; color: {TEXT}; selection-background-color: {BLUE};
}}
QLineEdit:focus {{ border: 2px solid {CYAN}; }}
QListView, QListWidget {{
    background: {BG}; border: none; color: {TEXT}; outline: none;
}}
QListWidget {{ background: {SURFACE}; border: 1px solid {CONTROL_BORDER}; border-radius: {RADIUS_S}px; padding: {XS}px; }}
QListWidget::item {{ padding: {S}px {M}px; border-radius: {RADIUS_S}px; }}
QListWidget::item:hover {{ background: {SURFACE_RAISED}; }}
QListWidget::item:selected {{ background: {SURFACE_PRESSED}; color: {TEXT}; }}
QListWidget:focus, QListView:focus {{ border: 1px solid {CYAN}; }}
QTextBrowser, QTextEdit, QPlainTextEdit {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: {RADIUS_S}px; padding: {S}px; selection-background-color: {SURFACE_PRESSED}; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_MUTED}; padding: {S}px {L}px; margin-right: {XS}px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {CYAN}; }}
QToolButton#continueCard {{
    background: {SURFACE}; color: {TEXT}; border-radius: {RADIUS_S}px; padding: {S}px;
}}
QToolButton#continueCard:hover {{ background: {SURFACE_RAISED}; }}

QStatusBar {{ background: {BG}; color: {TEXT_MUTED}; }}
QStatusBar::item {{ border: none; }}
"""


current_theme = DEFAULT_THEME
ACCENT_GRADIENT = _accent_gradient()
STYLESHEET = build_stylesheet()


def is_light() -> bool:
    return THEMES[current_theme].light


def apply_theme(key: str) -> None:
    """Switch every colour. The caller gives the application the new ``STYLESHEET``."""
    global ACCENT_GRADIENT, AMBER, BG, BLUE, BORDER, CONTROL_BORDER, CYAN, GREEN, ON_ACCENT, RED, STYLESHEET
    global SURFACE, SURFACE_PRESSED, SURFACE_RAISED, TEXT, TEXT_DISABLED, TEXT_MUTED, current_theme
    current_theme = key if key in THEMES else DEFAULT_THEME
    palette = THEMES[current_theme]
    BG, SURFACE, SURFACE_RAISED = palette.bg, palette.surface, palette.raised
    SURFACE_PRESSED, BORDER = palette.pressed, palette.border
    CONTROL_BORDER, TEXT_MUTED = palette.control_border, palette.muted
    BLUE, CYAN = palette.accent, palette.accent2
    TEXT, TEXT_DISABLED, ON_ACCENT = palette.text, palette.text_disabled, palette.on_accent
    RED, AMBER, GREEN = palette.red, palette.amber, palette.green
    ACCENT_GRADIENT = _accent_gradient()
    STYLESHEET = build_stylesheet()
