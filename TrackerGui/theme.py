"""Colours and the stylesheet: one dark, flat look for the whole window."""
from PySide6.QtGui import QColor

ACCENT = "#4f8cff"
BG = "#1b1d22"
PANEL = "#23262d"
PANEL_ALT = "#2a2e36"
BORDER = "#343943"
TEXT = "#e6e8ec"
MUTED = "#8a919e"

TYPE_COLORS = {"spec": "#3ecf8e", "feature": "#4f8cff", "bug": "#ff5f6d", "debt": "#c58fff", "problem": "#ffb44f"}
STATUS_COLORS = {"draft": MUTED, "open": TEXT, "doing": "#4fd1a1", "done": "#5f6b7a", "dropped": "#5f6b7a"}


def color(name, table):
    return QColor(table.get(name, TEXT))


STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; font-family: "Segoe UI", sans-serif; }}
QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QFrame#panel, QListWidget, QTableView, QPlainTextEdit, QTextEdit, QLineEdit, QComboBox, QSpinBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit#title {{ font-size: 18px; font-weight: 600; background: transparent; border: 1px solid transparent; }}
QLineEdit#title:hover, QLineEdit#title:focus {{ border-color: {BORDER}; background: {PANEL}; }}
QTableView {{ gridline-color: transparent; selection-background-color: {PANEL_ALT}; selection-color: {TEXT}; outline: 0; }}
QTableView::item {{ padding: 4px 6px; border: 0; }}
QHeaderView::section {{ background: {BG}; color: {MUTED}; border: 0; border-bottom: 1px solid {BORDER}; padding: 4px 6px; font-weight: 600; }}
QListWidget::item {{ padding: 4px 6px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {PANEL_ALT}; }}
QPushButton, QToolButton {{
    background: {PANEL_ALT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 10px; color: {TEXT};
}}
QPushButton:hover, QToolButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {MUTED}; border-color: {PANEL_ALT}; }}
QToolButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {PANEL_ALT}; border-color: {BORDER}; color: {MUTED}; font-weight: 400; }}
QPushButton#danger:hover {{ border-color: {TYPE_COLORS["bug"]}; color: {TYPE_COLORS["bug"]}; }}
QToolButton#chip {{ padding: 2px 8px; border-radius: 10px; font-size: 12px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#heading {{ color: {MUTED}; font-weight: 600; font-size: 11px; letter-spacing: 1px; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: {PANEL_ALT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QStatusBar {{ color: {MUTED}; border-top: 1px solid {BORDER}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background: {PANEL_ALT}; }}
QToolTip {{ background: {PANEL_ALT}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QDialog {{ background: {BG}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; border-radius: 3px; background: {PANEL}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
"""
