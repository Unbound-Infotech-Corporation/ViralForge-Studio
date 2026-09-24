from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from trendforge.bootstrap import assets_root
from trendforge.domain.enums import ThemeMode

DARK_QSS = """
* { font-family: "Segoe UI Variable", "Segoe UI", "Noto Sans", sans-serif; }
QMainWindow, QDialog, QWizard, QWidget { background: #12141A; color: #F2F4F8; }
QScrollArea { border: none; background: transparent; }
QLabel#title { font-size: 28px; font-weight: 700; color: #FFFFFF; }
QLabel#subtitle { font-size: 14px; color: #8B93A7; }
QLabel#kicker { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: #E8A54B; }
QFrame#card, QFrame#nav, QFrame#hero {
    background: #1A1D27;
    border: 1px solid #2C3142;
    border-radius: 14px;
}
QFrame#nav { background: #161822; border-radius: 0px; border: none; border-right: 1px solid #2C3142; }
QPushButton {
    background: #242836;
    color: #F2F4F8;
    border: 1px solid #343A4D;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #2E3344; border-color: #E8A54B; }
QPushButton:pressed { background: #1A1D27; }
QPushButton:disabled { color: #6A7286; background: #1A1D27; }
QPushButton#primary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #E8A54B, stop:1 #D4783A);
    color: #1A1208;
    border: none;
    padding: 12px 22px;
    font-size: 15px;
}
QPushButton#primary:hover { background: #F0B45C; }
QPushButton#nav {
    text-align: left;
    padding: 12px 16px;
    border: none;
    background: transparent;
    border-radius: 10px;
    font-size: 14px;
}
QPushButton#nav:checked { background: #2A3144; color: #E8A54B; border-left: 3px solid #E8A54B; }
QPushButton#nav:hover { background: #242836; color: #E8A54B; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {
    background: #12141A;
    border: 1px solid #2C3142;
    border-radius: 10px;
    padding: 8px 10px;
    color: #F2F4F8;
    selection-background-color: #E8A54B;
    selection-color: #1A1208;
}
QFrame#choiceRow {
    background: #12141A;
    border: 1px solid #3A4158;
    border-radius: 8px;
}
QFrame#choiceRow QComboBox {
    border: none;
    background: transparent;
    padding: 4px 6px;
}
QLabel#choiceTitle { color: #8B93A7; font-size: 12px; font-weight: 700; }
QLabel#choiceMark { background: transparent; border: none; }
QFrame#hintBar {
    background: #2A2418;
    border-bottom: 1px solid #E8A54B;
}
QPushButton#consoleToggle { padding: 2px 10px; border-radius: 6px; }
QComboBox QAbstractItemView {
    background: #1A1D27;
    color: #F2F4F8;
    selection-background-color: #E8A54B;
    selection-color: #1A1208;
    border: 1px solid #2C3142;
}
QProgressBar {
    background: #12141A;
    border: 1px solid #2C3142;
    border-radius: 8px;
    text-align: center;
    color: #F2F4F8;
    height: 18px;
}
QProgressBar::chunk { background: #E8A54B; border-radius: 8px; }
QTabBar::tab {
    background: #1A1D27; color: #8B93A7; padding: 8px 16px;
    border: 1px solid #2C3142; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px;
}
QTabBar::tab:selected { background: #242836; color: #E8A54B; }
QTabWidget::pane { border: 1px solid #2C3142; border-radius: 0 10px 10px 10px; }
QTableWidget, QListWidget, QTreeWidget {
    background: #1A1D27; border: 1px solid #2C3142; border-radius: 10px; gridline-color: #2C3142;
}
QHeaderView::section { background: #161822; color: #8B93A7; border: none; padding: 6px; }
QStatusBar { background: #161822; color: #8B93A7; }
QCheckBox, QRadioButton { spacing: 8px; }
QGroupBox { border: 1px solid #2C3142; border-radius: 12px; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #E8A54B; }
QToolTip { background: #1A1D27; color: #F2F4F8; border: 1px solid #E8A54B; padding: 6px; }
"""

LIGHT_QSS = """
* { font-family: "Segoe UI Variable", "Segoe UI", "Noto Sans", sans-serif; }
QMainWindow, QDialog, QWizard, QWidget { background: #F4F1EA; color: #1C1A16; }
QLabel#title { font-size: 28px; font-weight: 700; color: #1C1A16; }
QLabel#subtitle { font-size: 14px; color: #5C574E; }
QLabel#kicker { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: #B06A12; }
QFrame#card, QFrame#hero { background: #FFFBF4; border: 1px solid #E4D9C5; border-radius: 14px; }
QFrame#nav { background: #EFE7D8; border: none; border-right: 1px solid #E4D9C5; }
QPushButton {
    background: #FFFBF4; color: #1C1A16; border: 1px solid #E4D9C5;
    border-radius: 10px; padding: 8px 14px; font-weight: 600;
}
QPushButton:hover { border-color: #B06A12; }
QPushButton#primary {
    background: #E8A54B; color: #1A1208; border: none; padding: 12px 22px; font-size: 15px;
}
QPushButton#nav { text-align: left; padding: 12px 16px; border: none; background: transparent; border-radius: 10px; }
QPushButton#nav:checked, QPushButton#nav:hover { background: #FFFBF4; color: #B06A12; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {
    background: #FFFBF4; border: 1px solid #E4D9C5; border-radius: 10px; padding: 8px 10px;
}
QFrame#choiceRow { background: #FFFBF4; border: 1px solid #C9BBA4; border-radius: 8px; }
QFrame#choiceRow QComboBox { border: none; background: transparent; }
QLabel#choiceTitle { color: #5C574E; font-size: 12px; font-weight: 700; }
QFrame#hintBar { background: #F3E6CC; border-bottom: 1px solid #B06A12; }
QProgressBar { background: #EFE7D8; border: 1px solid #E4D9C5; border-radius: 8px; text-align: center; }
QProgressBar::chunk { background: #E8A54B; border-radius: 8px; }
QStatusBar { background: #EFE7D8; color: #5C574E; }
QTableWidget, QListWidget { background: #FFFBF4; border: 1px solid #E4D9C5; border-radius: 10px; }
"""


def apply_theme(app: QApplication, mode: ThemeMode) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_QSS if mode is ThemeMode.DARK else LIGHT_QSS)


def _paint_icon(size: int = 256) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#1A1D27"))
    grad.setColorAt(1, QColor("#3A2A18"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(8, 8, size - 16, size - 16, 48, 48)
    p.setBrush(QColor("#E8A54B"))
    c = pix.rect().center()
    p.drawPolygon([
        QPoint(c.x() - size // 8, c.y() + size // 6),
        QPoint(c.x() + size // 5, c.y()),
        QPoint(c.x() - size // 8, c.y() - size // 6),
    ])
    p.end()
    return pix


def load_app_icon() -> QIcon:
    png = assets_root() / "icons" / "trendforge.png"
    ico = assets_root() / "icons" / "trendforge.ico"
    if png.exists():
        return QIcon(str(png))
    if ico.exists():
        return QIcon(str(ico))
    pix = _paint_icon()
    try:
        png.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(png), "PNG")
    except OSError:
        pass
    icon = QIcon()
    icon.addPixmap(pix)
    return icon
