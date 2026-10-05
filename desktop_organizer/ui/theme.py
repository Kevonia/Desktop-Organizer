"""Light and dark themes built from one set of color tokens."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

TOKENS = {
    "light": {
        "window": "#f6f7f9", "base": "#ffffff", "alt": "#f2f4f7", "text": "#1c2128",
        "muted": "#5b6472", "border": "#d9dde3", "sidebar": "#eef1f5", "hover": "#e4e8ee",
        "accent": "#2563eb", "accent_hover": "#1d4ed8", "accent_text": "#ffffff",
        "warning_bg": "#fff4e5", "warning_text": "#8a4b00", "error": "#b42318",
    },
    "dark": {
        "window": "#1b1d21", "base": "#23262b", "alt": "#292d33", "text": "#e6e8eb",
        "muted": "#9aa3ad", "border": "#383d45", "sidebar": "#202328", "hover": "#2f343b",
        "accent": "#4c8dff", "accent_hover": "#6aa1ff", "accent_text": "#0b1220",
        "warning_bg": "#3a2a12", "warning_text": "#fdb022", "error": "#f97066",
    },
}

_current = "light"


def resolve(choice: str) -> str:
    if choice in ("light", "dark"):
        return choice
    hints = QApplication.styleHints()
    return "dark" if hints.colorScheme() == Qt.ColorScheme.Dark else "light"


def color(name: str) -> str:
    return TOKENS[_current][name]


def apply_theme(app: QApplication, choice: str) -> None:
    global _current
    _current = resolve(choice)
    t = TOKENS[_current]
    app.setStyle("Fusion")

    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["window"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["base"],
        QPalette.ColorRole.AlternateBase: t["alt"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.Button: t["base"],
        QPalette.ColorRole.ButtonText: t["text"],
        QPalette.ColorRole.ToolTipBase: t["base"],
        QPalette.ColorRole.ToolTipText: t["text"],
        QPalette.ColorRole.PlaceholderText: t["muted"],
        QPalette.ColorRole.Highlight: t["accent"],
        QPalette.ColorRole.HighlightedText: t["accent_text"],
        QPalette.ColorRole.Link: t["accent"],
        QPalette.ColorRole.Mid: t["border"],
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(_stylesheet(t))


def _stylesheet(t: dict[str, str]) -> str:
    return f"""
    QWidget {{ font-size: 10pt; }}
    #Sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
    #Sidebar QListWidget {{ background: transparent; border: none; outline: none; }}
    #Sidebar QListWidget::item {{ padding: 8px 10px; border-radius: 6px; margin: 1px 0; }}
    #Sidebar QListWidget::item:hover {{ background: {t['hover']}; }}
    #Sidebar QListWidget::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}
    #SectionLabel {{ color: {t['muted']}; font-size: 9pt; font-weight: 600; letter-spacing: 0.5px; }}
    #Title {{ font-size: 17pt; font-weight: 600; }}
    #Muted {{ color: {t['muted']}; }}
    #Warning {{ background: {t['warning_bg']}; color: {t['warning_text']};
                border-radius: 6px; padding: 8px 12px; }}
    #Error {{ color: {t['error']}; }}
    #EmptyState {{ color: {t['muted']}; font-size: 12pt; }}
    QPushButton {{ padding: 6px 14px; border: 1px solid {t['border']}; border-radius: 6px;
                   background: {t['base']}; }}
    QPushButton:hover {{ background: {t['hover']}; }}
    QPushButton:disabled {{ color: {t['muted']}; }}
    QPushButton#Primary {{ background: {t['accent']}; color: {t['accent_text']};
                           border: 1px solid {t['accent']}; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: {t['accent_hover']}; }}
    QPushButton#Primary:disabled {{ background: {t['border']}; border-color: {t['border']}; color: {t['muted']}; }}
    QPushButton#Token {{ padding: 3px 8px; font-family: Consolas, Menlo, monospace; }}
    QLineEdit, QComboBox, QPlainTextEdit {{ padding: 5px 8px; border: 1px solid {t['border']};
                                           border-radius: 6px; background: {t['base']}; }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
    QTreeWidget, QTableWidget {{ border: 1px solid {t['border']}; border-radius: 6px;
                                 background: {t['base']}; alternate-background-color: {t['alt']}; }}
    QHeaderView::section {{ background: {t['alt']}; padding: 6px; border: none;
                            border-bottom: 1px solid {t['border']}; font-weight: 600; }}
    QProgressBar {{ border: 1px solid {t['border']}; border-radius: 6px; text-align: center; height: 18px; }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 5px; }}
    """
