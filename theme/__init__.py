"""Apply VelaGuard Host Fusion + QSS theme."""

from pathlib import Path

from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import QApplication

from . import palette as pal


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei UI", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    qp = QPalette()
    qp.setColor(QPalette.Window, QColor(pal.BG))
    qp.setColor(QPalette.WindowText, QColor(pal.TEXT))
    qp.setColor(QPalette.Base, QColor(pal.SURFACE))
    qp.setColor(QPalette.AlternateBase, QColor("#1E2228"))
    qp.setColor(QPalette.Text, QColor(pal.TEXT))
    qp.setColor(QPalette.Button, QColor(pal.SURFACE))
    qp.setColor(QPalette.ButtonText, QColor(pal.TEXT))
    qp.setColor(QPalette.Highlight, QColor(pal.ACCENT))
    qp.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    qp.setColor(QPalette.ToolTipBase, QColor(pal.SURFACE))
    qp.setColor(QPalette.ToolTipText, QColor(pal.TEXT))
    qp.setColor(QPalette.PlaceholderText, QColor(pal.MUTED))
    qp.setColor(QPalette.Disabled, QPalette.Text, QColor(pal.OFFLINE))
    qp.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(pal.OFFLINE))
    app.setPalette(qp)

    qss_path = Path(__file__).with_name("velaguard.qss")
    app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
