from __future__ import annotations

import random
import sys
from functools import partial

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from robotic_face_widget import RoboticFaceWidget


class ControlPanel(QWidget):
    def __init__(self, face: RoboticFaceWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.face = face
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(2600)
        self._cycle_timer.timeout.connect(self._advance_cycle)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel("Emotion")
        title.setStyleSheet("font-size: 18px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(title)

        self.emotion_combo = QComboBox()
        self.emotion_combo.addItems(self.face.available_emotions())
        self.emotion_combo.currentTextChanged.connect(self.face.set_emotion)
        layout.addWidget(self.emotion_combo)

        self.cycle_checkbox = QCheckBox("Cycle emotions")
        self.cycle_checkbox.toggled.connect(self._toggle_cycle)
        layout.addWidget(self.cycle_checkbox)

        layout.addSpacing(20)

        orient_title = QLabel("Orientation")
        orient_title.setStyleSheet("font-size: 18px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(orient_title)

        self.sliders = {}
        grid = QGridLayout()
        grid.setVerticalSpacing(16)
        grid.setHorizontalSpacing(12)
        layout.addLayout(grid)

        for row, (axis, rng) in enumerate((("yaw", 45), ("pitch", 30), ("roll", 25))):
            label = QLabel(axis.upper())
            label.setStyleSheet("font-size: 14px; font-weight: 500;")
            grid.addWidget(label, row, 0)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-rng, rng)
            slider.setValue(0)
            slider.setSingleStep(1)
            slider.valueChanged.connect(partial(self._update_orientation, axis))
            grid.addWidget(slider, row, 1)
            self.sliders[axis] = slider

            value_label = QLabel("0°")
            value_label.setObjectName(f"value_{axis}")
            value_label.setFixedWidth(48)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(value_label, row, 2)

        layout.addSpacing(10)

        reset_btn = QPushButton("Reset Orientation")
        reset_btn.clicked.connect(self._reset_orientation)
        layout.addWidget(reset_btn)

        shuffle_btn = QPushButton("Surprise Me ✨")
        shuffle_btn.clicked.connect(self._random_emotion)
        layout.addWidget(shuffle_btn)

        layout.addSpacerItem(QSpacerItem(20, 40))

        tip = QLabel("Use the controls to explore the face's expressiveness.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 12px;")
        layout.addWidget(tip)

        layout.addStretch(1)

    def _update_orientation(self, axis: str, value: int) -> None:
        getattr(self.face, "set_orientation")(**{axis: float(value)})
        label = self.findChild(QLabel, f"value_{axis}")
        if label:
            label.setText(f"{value}°")

    def _reset_orientation(self) -> None:
        self.face.set_orientation(yaw=0.0, pitch=0.0, roll=0.0)
        for axis, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)
            label = self.findChild(QLabel, f"value_{axis}")
            if label:
                label.setText("0°")

    def _random_emotion(self) -> None:
        emotions = list(self.face.available_emotions())
        if not emotions:
            return
        current_text = self.emotion_combo.currentText()
        choices = [emotion for emotion in emotions if emotion != current_text]
        next_emotion = random.choice(choices or emotions)
        self.emotion_combo.setCurrentText(next_emotion)

    def _toggle_cycle(self, enabled: bool) -> None:
        if enabled and len(self.face.available_emotions()) > 1:
            self._cycle_timer.start()
        else:
            self._cycle_timer.stop()

    def _advance_cycle(self) -> None:
        emotions = list(self.face.available_emotions())
        if len(emotions) < 2:
            return
        current_text = self.emotion_combo.currentText()
        try:
            index = emotions.index(current_text)
        except ValueError:
            index = -1
        next_emotion = emotions[(index + 1) % len(emotions)]
        if next_emotion != current_text:
            self.emotion_combo.setCurrentText(next_emotion)


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Robotic Face Widget")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        self.face = RoboticFaceWidget()
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setLayout(QVBoxLayout())
        frame.layout().addWidget(self.face)
        frame.layout().setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame, 3)

        panel = ControlPanel(self.face)
        panel.setFixedWidth(240)
        panel.setObjectName("controlPanel")
        layout.addWidget(panel, 1)

        self.face.set_emotion("happy")


def _apply_dark_palette(app: QApplication) -> None:
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
        QLabel { font-size: 13px; }
        #controlPanel { background: rgba(12, 14, 26, 0.6); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 18px; }
        """
    )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Robotic Face Demo")
    app.setStyle("Fusion")
    _apply_dark_palette(app)

    window = MainWindow()
    window.resize(1024, 640)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
