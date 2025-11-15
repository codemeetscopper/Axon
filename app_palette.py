from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_dark_palette(app: QApplication) -> None:
    """Apply the shared dark palette used across demos and runtime."""

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(12, 14, 26))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(20, 22, 36))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(16, 18, 30))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(26, 28, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Highlight, QColor(90, 240, 210))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(12, 14, 26))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 110, 180))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget { color: white; }
        QComboBox, QSlider, QPushButton { font-size: 14px; }
        QPushButton { background-color: rgba(90, 240, 210, 0.2); border: 1px solid rgba(90,240,210,0.4); padding: 8px 12px; border-radius: 6px; }
        QPushButton:hover { background-color: rgba(90, 240, 210, 0.32); }
        QPushButton:pressed { background-color: rgba(90, 240, 210, 0.45); }
        QComboBox { background-color: rgba(26, 28, 45, 0.9); border: 1px solid rgba(90,240,210,0.5); padding: 6px; border-radius: 6px; }
        QSlider::groove:horizontal { height: 6px; background: rgba(255,255,255,0.2); border-radius: 3px; }
        QSlider::handle:horizontal { background: rgba(90,240,210,0.9); width: 18px; margin: -6px 0; border-radius: 9px; }
        """
    )


# Backwards compatibility for modules that still import the old helper name.
_apply_dark_palette = apply_dark_palette
