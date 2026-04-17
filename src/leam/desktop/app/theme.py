"""Shared visual theme helpers for LEAM Desktop."""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

PALETTE: Dict[str, str] = {
    "bg_app": "#0a0d0f",
    "bg_panel": "#11171a",
    "bg_panel_alt": "#161e21",
    "bg_panel_soft": "#1c2629",
    "bg_input": "#0d1214",
    "bg_hover": "#1c2b2d",
    "border": "#263236",
    "border_strong": "#56736e",
    "text_primary": "#edf1ee",
    "text_secondary": "#a0aba7",
    "text_muted": "#6f7b77",
    "accent": "#8db7ab",
    "accent_strong": "#6f958a",
    "accent_soft": "#1b322c",
    "warning": "#d0ab74",
    "danger": "#d07d7a",
    "success": "#94b08b",
    "idle": "#77817d",
    "selection": "#223131",
}

STATUS_TONES: Dict[str, str] = {
    "idle": "idle",
    "waiting": "muted",
    "running": "info",
    "success": "success",
    "issues": "warning",
    "blocked_by_upstream": "muted",
    "rerun_required": "danger",
    "stale": "warning",
    "error": "danger",
}

_TONE_COLORS: Dict[str, str] = {
    "idle": PALETTE["idle"],
    "muted": PALETTE["text_muted"],
    "info": PALETTE["accent"],
    "success": PALETTE["success"],
    "warning": PALETTE["warning"],
    "danger": PALETTE["danger"],
    "accent": PALETTE["accent"],
}


def build_stylesheet() -> str:
    """Return the desktop stylesheet."""

    return f"""
QWidget {{
    background: {PALETTE["bg_app"]};
    color: {PALETTE["text_primary"]};
    font-family: "Segoe UI";
    font-size: 9pt;
}}

QLabel {{
    background: transparent;
}}

QMainWindow, QDialog {{
    background: {PALETTE["bg_app"]};
}}

QMenuBar {{
    background: {PALETTE["bg_panel"]};
    color: {PALETTE["text_primary"]};
    border-bottom: 1px solid {PALETTE["border"]};
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 10px;
}}

QMenuBar::item:selected {{
    background: {PALETTE["bg_hover"]};
}}

QMenu {{
    background: {PALETTE["bg_panel"]};
    color: {PALETTE["text_primary"]};
    border: 1px solid {PALETTE["border"]};
}}

QMenu::item:selected {{
    background: {PALETTE["bg_hover"]};
}}

QStatusBar {{
    background: {PALETTE["bg_panel"]};
    color: {PALETTE["text_secondary"]};
    border-top: 1px solid {PALETTE["border"]};
}}

QSplitter::handle {{
    background: {PALETTE["border"]};
    width: 2px;
}}

QGroupBox {{
    background: {PALETTE["bg_panel"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 14px;
    margin-top: 14px;
    padding: 10px 12px 12px 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {PALETTE["accent"]};
}}

QFrame#LaunchHeroCard,
QFrame#LaunchCard,
QFrame#TopChromeCard,
QFrame#WorkspaceCard,
QFrame#ConsoleCard,
QFrame#ActionCard,
QFrame#StepHeaderCard,
QFrame#RunStateCard {{
    background: {PALETTE["bg_panel"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 16px;
}}

QFrame#LaunchHeroCard {{
    border: 1px solid {PALETTE["border_strong"]};
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 {PALETTE["bg_panel_alt"]},
        stop: 1 {PALETTE["bg_panel"]}
    );
}}

QFrame#TopChromeCard,
QFrame#WorkspaceCard,
QFrame#StepHeaderCard {{
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 {PALETTE["bg_panel_alt"]},
        stop: 1 {PALETTE["bg_panel"]}
    );
}}

QLabel[role="eyebrow"] {{
    color: {PALETTE["accent"]};
    font-size: 8pt;
    font-weight: 700;
}}

QLabel[role="heroTitle"] {{
    font-size: 21pt;
    font-weight: 700;
}}

QLabel[role="title"] {{
    font-size: 15pt;
    font-weight: 700;
}}

QLabel[role="subtitle"] {{
    color: {PALETTE["text_secondary"]};
    font-size: 10pt;
}}

QLabel[role="muted"] {{
    color: {PALETTE["text_muted"]};
}}

QLabel[role="value"] {{
    font-size: 11pt;
    font-weight: 600;
}}

QLabel[pill="true"] {{
    border-radius: 10px;
    padding: 4px 10px;
    font-size: 8pt;
    font-weight: 700;
    color: {PALETTE["text_primary"]};
    background: {PALETTE["accent_soft"]};
    border: 1px solid {PALETTE["border_strong"]};
}}

QLabel[pill="true"][tone="idle"] {{
    background: #171d1f;
    border-color: #344044;
    color: {PALETTE["idle"]};
}}

QLabel[pill="true"][tone="muted"] {{
    background: #141a1c;
    border-color: #293437;
    color: {PALETTE["text_muted"]};
}}

QLabel[pill="true"][tone="info"] {{
    background: #172723;
    border-color: {PALETTE["accent_strong"]};
    color: {PALETTE["accent"]};
}}

QLabel[pill="true"][tone="success"] {{
    background: #19221b;
    border-color: #627960;
    color: {PALETTE["success"]};
}}

QLabel[pill="true"][tone="warning"] {{
    background: #2a2218;
    border-color: #836947;
    color: {PALETTE["warning"]};
}}

QLabel[pill="true"][tone="danger"] {{
    background: #2b1a1b;
    border-color: #855351;
    color: {PALETTE["danger"]};
}}

QLabel[role="statusText"][tone="muted"] {{
    color: {PALETTE["text_muted"]};
}}

QLabel[role="statusText"][tone="success"] {{
    color: {PALETTE["success"]};
}}

QLabel[role="statusText"][tone="warning"] {{
    color: {PALETTE["warning"]};
}}

QLabel[role="statusText"][tone="danger"] {{
    color: {PALETTE["danger"]};
}}

QLabel[role="statusText"][tone="info"] {{
    color: {PALETTE["accent"]};
}}

QPushButton {{
    background: {PALETTE["bg_panel_soft"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 12px;
    padding: 10px 14px;
    color: {PALETTE["text_primary"]};
    font-weight: 600;
}}

QPushButton:hover {{
    background: {PALETTE["bg_hover"]};
    border-color: {PALETTE["border_strong"]};
}}

QPushButton:pressed {{
    background: {PALETTE["accent_soft"]};
}}

QPushButton:disabled {{
    color: {PALETTE["text_muted"]};
    border-color: {PALETTE["border"]};
    background: #0f1416;
}}

QPushButton#PrimaryActionButton,
QPushButton#LaunchPrimaryButton {{
    background: {PALETTE["accent_soft"]};
    border-color: {PALETTE["border_strong"]};
    color: {PALETTE["accent"]};
    font-size: 10pt;
}}

QPushButton#PrimaryActionButton:hover,
QPushButton#LaunchPrimaryButton:hover {{
    background: #294640;
    color: {PALETTE["text_primary"]};
}}

QPushButton#LaunchGhostButton {{
    background: transparent;
    border-color: {PALETTE["border_strong"]};
    color: {PALETTE["text_secondary"]};
}}

QLineEdit,
QPlainTextEdit,
QListWidget,
QTableWidget,
QComboBox {{
    background: {PALETTE["bg_input"]};
    color: {PALETTE["text_primary"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 12px;
    padding: 8px 10px;
    selection-background-color: {PALETTE["selection"]};
    selection-color: {PALETTE["text_primary"]};
}}

QLineEdit:focus,
QPlainTextEdit:focus,
QListWidget:focus,
QTableWidget:focus,
QComboBox:focus {{
    border-color: {PALETTE["border_strong"]};
}}

QListWidget::item {{
    padding: 8px;
    margin: 4px;
    border-radius: 10px;
}}

QListWidget::item:selected {{
    background: {PALETTE["bg_hover"]};
    color: {PALETTE["text_primary"]};
}}

QListWidget::item:hover:!selected {{
    background: {PALETTE["bg_panel_soft"]};
}}

QListWidget#WorkflowRailList {{
    border: 1px solid {PALETTE["border"]};
    border-radius: 14px;
    padding: 8px;
}}

QListWidget#WorkflowRailList::item {{
    margin: 0;
    padding: 0;
    background: transparent;
}}

QListWidget#WorkflowRailList::item:selected {{
    background: transparent;
}}

QListWidget#WorkflowRailList::item:hover:!selected {{
    background: transparent;
}}

QTableWidget {{
    gridline-color: {PALETTE["border"]};
}}

QCheckBox {{
    spacing: 10px;
    color: {PALETTE["text_secondary"]};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {PALETTE["border"]};
    background: {PALETTE["bg_input"]};
}}

QCheckBox::indicator:hover {{
    border-color: {PALETTE["border_strong"]};
}}

QCheckBox::indicator:checked {{
    background: {PALETTE["accent_soft"]};
    border-color: {PALETTE["accent_strong"]};
}}

QCheckBox::indicator:checked:disabled {{
    background: {PALETTE["accent_soft"]};
    border-color: {PALETTE["accent_strong"]};
}}

QCheckBox::indicator:disabled {{
    background: #0f1416;
    border-color: {PALETTE["border"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background: {PALETTE["bg_panel"]};
    color: {PALETTE["text_primary"]};
    selection-background-color: {PALETTE["bg_hover"]};
}}

QTabWidget::pane {{
    border: 1px solid {PALETTE["border"]};
    border-radius: 14px;
    top: -1px;
    background: {PALETTE["bg_panel"]};
}}

QTabBar::tab {{
    background: transparent;
    color: {PALETTE["text_muted"]};
    padding: 10px 16px;
    margin-right: 4px;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    color: {PALETTE["accent"]};
    border-bottom-color: {PALETTE["accent"]};
}}

QHeaderView::section {{
    background: {PALETTE["bg_panel_soft"]};
    color: {PALETTE["text_secondary"]};
    border: none;
    border-bottom: 1px solid {PALETTE["border"]};
    padding: 8px;
    font-weight: 600;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 4px 0 4px 0;
}}

QScrollBar::handle:vertical {{
    background: {PALETTE["border"]};
    border-radius: 6px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {PALETTE["border_strong"]};
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0 4px 0 4px;
}}

QScrollBar::handle:horizontal {{
    background: {PALETTE["border"]};
    border-radius: 6px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {PALETTE["border_strong"]};
}}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {{
    background: transparent;
    border: none;
}}

QProgressBar {{
    border: 1px solid {PALETTE["border"]};
    border-radius: 8px;
    background: {PALETTE["bg_input"]};
    min-height: 10px;
}}

QProgressBar::chunk {{
    background: {PALETTE["accent"]};
    border-radius: 7px;
}}

QFrame[stepItem="true"] {{
    background: {PALETTE["bg_input"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 14px;
}}

QFrame[stepItem="true"][selected="true"] {{
    border-color: {PALETTE["accent_strong"]};
    background: {PALETTE["bg_hover"]};
}}
"""


def apply_theme(app_or_widget: QApplication | QWidget) -> None:
    """Apply the LEAM desktop theme."""

    app_or_widget.setStyleSheet(build_stylesheet())


def refresh_style(widget: QWidget) -> None:
    """Refresh stylesheet-driven dynamic properties."""

    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_role(widget: QWidget, role: str) -> None:
    """Set one semantic role used by the stylesheet."""

    widget.setProperty("role", role)
    refresh_style(widget)


def set_tone(widget: QWidget, tone: str) -> None:
    """Set one semantic tone used by the stylesheet."""

    widget.setProperty("tone", tone)
    refresh_style(widget)


def status_tone(status: str) -> str:
    """Map one workflow status to a theme tone."""

    return STATUS_TONES.get(status, "muted")


def status_qcolor(status: str) -> QColor:
    """Return one QColor for a workflow status."""

    tone = status_tone(status)
    return QColor(_TONE_COLORS.get(tone, PALETTE["text_muted"]))
